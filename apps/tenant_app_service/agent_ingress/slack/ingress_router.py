"""Slack public webhook router (platform-specific).

URLs use the shared ``/ingress/{endpoint_key}/...`` prefix but this module is
Slack-only: signing-secret verification, Events API, and Block Kit interactivity.

Handles:
  1. URL verification challenge
  2. Signature verification (X-Slack-Signature + X-Slack-Request-Timestamp)
  3. Endpoint resolution from endpoint_key path param
  4. Event dedupe via DB table
  5. Background processing (ack 200 within 3s, process chat async)
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.db.session import get_db
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.domain import (
    SlackMessageEvent,
    describe_ignored_event,
    parse_app_mention_event,
    parse_message_event,
    parse_thread_reply_event,
    slack_signature_failure_reason,
)
from apps.tenant_app_service.agent_ingress.slack.ingress_service import SlackIngressService
from apps.tenant_app_service.agent_ingress.slack.interactivity_service import (
    SlackInteractivityService,
    parse_interactivity_payload,
)
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository

logger = get_logger(__name__)

router = APIRouter(tags=["slack-webhook"], include_in_schema=False)


@router.post("/ingress/{endpoint_key}/events")
async def slack_events_webhook(
    endpoint_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Slack Events API webhook. Verified by signing secret, not JWT."""
    raw_body = await request.body()
    body_text = raw_body.decode("utf-8")
    repo = SlackRepository(db)
    endpoint = await repo.get_endpoint_by_key(endpoint_key)
    return await _handle_slack_events(
        request=request,
        body_text=body_text,
        endpoint=endpoint,
        endpoint_label=endpoint_key,
        db=db,
        repo=repo,
    )


async def _handle_slack_events(
    *,
    request: Request,
    body_text: str,
    endpoint: AgentIngressEndpoint | None,
    endpoint_label: str,
    db: AsyncSession,
    repo: SlackRepository,
) -> JSONResponse:
    try:
        payload = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "invalid_json"})

    payload_type = payload.get("type") or "unknown"

    if not endpoint:
        logger.warning("Slack webhook rejected %s endpoint_found=False", endpoint_label)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "integration_not_found"})

    signing_secret = repo.decrypt_signing_secret(endpoint)
    slack_signature = request.headers.get("X-Slack-Signature", "")
    slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")

    signature_failure = slack_signature_failure_reason(
        signing_secret=signing_secret,
        timestamp=slack_timestamp,
        body=body_text,
        signature=slack_signature,
    )
    if signature_failure:
        logger.warning(
            "Slack signature verification failed %s reason=%s",
            endpoint_label,
            signature_failure,
        )
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "invalid_signature"})

    if payload_type == "url_verification":
        challenge = payload.get("challenge", "")
        logger.info("Slack url_verification challenge received %s", endpoint_label)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"challenge": challenge})

    if not endpoint.enabled:
        event = payload.get("event") or {}
        message_event = _parse_slack_event(event, event_id=payload.get("event_id"))
        if message_event:
            logger.info(
                "Slack webhook disabled %s event_id=%s user_id=%s",
                endpoint_label,
                message_event.event_id,
                message_event.user_id,
            )
            await db.commit()
            asyncio.create_task(_safe_notify_disabled(message_event, endpoint.id))
        else:
            logger.info(
                "Slack webhook disabled %s ignored event_id=%s reason=%s",
                endpoint_label,
                payload.get("event_id"),
                describe_ignored_event(event),
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "disabled"})

    event = payload.get("event") or {}
    event_id = payload.get("event_id")
    message_event = _parse_slack_event(event, event_id=event_id)
    if message_event is None:
        logger.info(
            "Slack webhook ignored %s event_id=%s reason=%s",
            endpoint_label,
            event_id,
            describe_ignored_event(event),
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ignored"})

    configured_team_id = repo.slack_team_id(endpoint)
    if configured_team_id and message_event.team_id and message_event.team_id != configured_team_id:
        logger.warning(
            "Slack team_id mismatch: event=%s configured=%s %s",
            message_event.team_id,
            configured_team_id,
            endpoint_label,
        )
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"error": "team_mismatch"})

    already_processed = await repo.is_event_processed(endpoint.tenant_id, message_event.event_id)
    if already_processed:
        logger.info(
            "Slack duplicate event %s for tenant %s, acking",
            message_event.event_id,
            endpoint.tenant_id,
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "duplicate"})

    logger.info(
        "Slack webhook accepted tenant=%s %s event_id=%s user_id=%s",
        endpoint.tenant_id,
        endpoint_label,
        message_event.event_id,
        message_event.user_id,
    )
    await db.commit()
    asyncio.create_task(_safe_handle(message_event, endpoint.id))

    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


def _parse_slack_event(event: dict, *, event_id: str | None) -> SlackMessageEvent | None:
    event_type = event.get("type")
    if event_type == "message":
        parsed = parse_message_event(event, event_id=event_id)
        if parsed is None and event.get("thread_ts"):
            parsed = parse_thread_reply_event(event, event_id=event_id)
        return parsed
    if event_type == "app_mention":
        return parse_app_mention_event(event, event_id=event_id)
    return None


async def _safe_handle(event: SlackMessageEvent, endpoint_id: int) -> None:
    from apps.shared.db.session import app_db_session

    try:
        async with app_db_session() as bg_db:
            ingress = SlackIngressService(bg_db)
            await ingress.handle_message(event, endpoint_id)
    except Exception:
        logger.exception("Slack ingress background task failed for endpoint %s", endpoint_id)


@router.post("/ingress/{endpoint_key}/interactions")
async def slack_interactions_webhook(
    endpoint_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Slack interactivity webhook for feedback buttons and modals."""
    raw_body = await request.body()
    body_text = raw_body.decode("utf-8")
    repo = SlackRepository(db)
    endpoint = await repo.get_endpoint_by_key(endpoint_key)
    if not endpoint:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "integration_not_found"})

    signing_secret = repo.decrypt_signing_secret(endpoint)
    slack_signature = request.headers.get("X-Slack-Signature", "")
    slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")

    signature_failure = slack_signature_failure_reason(
        signing_secret=signing_secret,
        timestamp=slack_timestamp,
        body=body_text,
        signature=slack_signature,
    )
    if signature_failure:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "invalid_signature"})

    payload = parse_interactivity_payload(body_text)
    if not payload:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "invalid_payload"})

    interactivity = SlackInteractivityService(db)
    response_body = await interactivity.handle_payload(payload, endpoint)
    return JSONResponse(status_code=status.HTTP_200_OK, content=response_body)


async def _safe_notify_disabled(event: SlackMessageEvent, endpoint_id: int) -> None:
    from apps.shared.db.session import app_db_session

    try:
        async with app_db_session() as bg_db:
            ingress = SlackIngressService(bg_db)
            await ingress.notify_disabled(event, endpoint_id)
    except Exception:
        logger.exception("Slack disabled notification failed for endpoint %s", endpoint_id)
