"""Slack public webhook router (platform-specific).

Presentation: HTTP I/O, signing headers, status mapping. Admission and chat
orchestration live in ``ingress_service`` and ``domain``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.session import get_db
from apps.tenant_app_service.agent_ingress.slack.ingress_http import slack_events_ingress_http_response
from apps.tenant_app_service.agent_ingress.slack.ingress_results import (
    SlackEventsIngressResultKind,
    SlackInteractivityIngressResultKind,
)
from apps.tenant_app_service.agent_ingress.slack.ingress_service import SlackIngressService
from apps.tenant_app_service.agent_ingress.slack.webhook_auth import SlackWebhookAuthFailure

router = APIRouter(tags=["slack-webhook"], include_in_schema=False)


async def _slack_webhook_body_text(request: Request) -> str:
    return (await request.body()).decode("utf-8")


def _slack_signing_headers(request: Request) -> tuple[str, str]:
    return (
        request.headers.get("X-Slack-Request-Timestamp", ""),
        request.headers.get("X-Slack-Signature", ""),
    )


def _slack_webhook_auth_http_response(failure: SlackWebhookAuthFailure) -> tuple[int, dict[str, str]]:
    if failure.error == "integration_not_found":
        return 404, {"error": "integration_not_found"}
    return 401, {"error": "invalid_signature"}


def _webhook_auth_json_response(failure: SlackWebhookAuthFailure) -> JSONResponse:
    http_status, body = _slack_webhook_auth_http_response(failure)
    return JSONResponse(status_code=http_status, content=body)


@router.post("/ingress/{endpoint_key}/events")
async def slack_events_webhook(
    endpoint_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Slack Events API webhook. Verified by signing secret, not JWT."""
    body_text = await _slack_webhook_body_text(request)
    slack_timestamp, slack_signature = _slack_signing_headers(request)
    try:
        payload = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "invalid_json"})

    ingress = SlackIngressService(db)
    result = await ingress.process_events_webhook(
        endpoint_key=endpoint_key,
        payload=payload,
        body_text=body_text,
        slack_timestamp=slack_timestamp,
        slack_signature=slack_signature,
    )
    if result.kind == SlackEventsIngressResultKind.AUTH_FAILED:
        assert result.auth_failure is not None
        return _webhook_auth_json_response(result.auth_failure)
    http_status, body = slack_events_ingress_http_response(result)
    return JSONResponse(status_code=http_status, content=body)


@router.post("/ingress/{endpoint_key}/interactions")
async def slack_interactions_webhook(
    endpoint_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Slack interactivity webhook for feedback buttons and modals."""
    body_text = await _slack_webhook_body_text(request)
    slack_timestamp, slack_signature = _slack_signing_headers(request)

    ingress = SlackIngressService(db)
    result = await ingress.process_interactions_webhook(
        endpoint_key=endpoint_key,
        body_text=body_text,
        slack_timestamp=slack_timestamp,
        slack_signature=slack_signature,
    )
    if result.kind == SlackInteractivityIngressResultKind.AUTH_FAILED:
        assert result.auth_failure is not None
        return _webhook_auth_json_response(result.auth_failure)
    if result.kind == SlackInteractivityIngressResultKind.INVALID_PAYLOAD:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "invalid_payload"})
    return JSONResponse(status_code=status.HTTP_200_OK, content=result.response_body or {})
