"""Handle Slack Block Kit interactivity for message feedback."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.access import resolve_eligible_slack_user_id
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort, SlackWebClient
from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import (
    ACTION_FEEDBACK_NEGATIVE,
    ACTION_FEEDBACK_POSITIVE,
    VIEW_FEEDBACK_COMMENT,
    build_feedback_blocks,
    build_feedback_comment_modal,
)
from apps.tenant_app_service.agent_ingress.slack.identity_service import SlackIdentityService
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.message_feedback.domain import (
    FEEDBACK_RATING_NEGATIVE,
    FEEDBACK_RATING_POSITIVE,
    FEEDBACK_SOURCE_SLACK,
)
from apps.tenant_app_service.message_feedback.service import MessageFeedbackService

logger = get_logger(__name__)


class SlackInteractivityService:
    """Process Slack interactive payloads (feedback buttons + comment modal)."""

    def __init__(
        self,
        db: AsyncSession,
        client: SlackClientPort | None = None,
        identity_service: SlackIdentityService | None = None,
    ):
        self.db = db
        self.repo = SlackRepository(db)
        self.client = client or SlackWebClient()
        self.identity_service = identity_service or SlackIdentityService(db, client=client)

    async def handle_payload(self, payload: dict[str, Any], endpoint: AgentIngressEndpoint) -> dict[str, Any]:
        payload_type = payload.get("type")
        if payload_type == "block_actions":
            return await self._handle_block_actions(payload, endpoint)
        if payload_type == "view_submission":
            return await self._handle_view_submission(payload, endpoint)
        return {}

    async def _handle_block_actions(self, payload: dict[str, Any], endpoint: AgentIngressEndpoint) -> dict[str, Any]:
        actions = payload.get("actions") or []
        if not actions:
            return {}
        action = actions[0]
        action_id = action.get("action_id")
        message_id = action.get("value")
        if not message_id:
            return {}

        if action_id not in {ACTION_FEEDBACK_POSITIVE, ACTION_FEEDBACK_NEGATIVE}:
            return {}

        slack_user_id = (payload.get("user") or {}).get("id", "")
        user_id = await resolve_eligible_slack_user_id(
            self.db,
            tenant_id=endpoint.tenant_id,
            slack_user_id=slack_user_id,
            endpoint=endpoint,
            identity_service=self.identity_service,
        )
        if user_id is None:
            logger.warning("Slack feedback denied for user %s on tenant %s", slack_user_id, endpoint.tenant_id)
            return {}

        channel = (payload.get("channel") or {}).get("id") or (payload.get("container") or {}).get("channel_id")
        message_ts = (payload.get("message") or {}).get("ts") or (payload.get("container") or {}).get("message_ts")
        external_ref = {"channel_id": channel, "message_ts": message_ts} if channel and message_ts else None

        rating = FEEDBACK_RATING_POSITIVE if action_id == ACTION_FEEDBACK_POSITIVE else FEEDBACK_RATING_NEGATIVE

        feedback_service = MessageFeedbackService(endpoint.tenant_id, self.db)
        await feedback_service.upsert_feedback_for_message_id(
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            source=FEEDBACK_SOURCE_SLACK,
            external_ref=external_ref,
        )

        message = payload.get("message") or {}
        original_text = _extract_text_from_blocks(message.get("blocks")) or message.get("text", "")
        updated_blocks = build_feedback_blocks(original_text, message_id, current_rating=rating)

        bot_token = self.repo.decrypt_bot_token(endpoint)
        if channel and message_ts:
            try:
                await self.client.chat_update(
                    bot_token=bot_token,
                    channel=channel,
                    ts=message_ts,
                    text=original_text,
                    blocks=updated_blocks,
                )
            except Exception:
                logger.exception("Failed to update Slack message after feedback")

        if action_id == ACTION_FEEDBACK_NEGATIVE:
            trigger_id = payload.get("trigger_id")
            if trigger_id:
                modal = build_feedback_comment_modal(message_id=message_id, trigger_id=trigger_id)
                try:
                    await self.client.views_open(
                        bot_token=bot_token,
                        trigger_id=modal["trigger_id"],
                        view=modal["view"],
                    )
                except Exception:
                    logger.exception("Failed to open Slack feedback comment modal")

        return {}

    async def _handle_view_submission(self, payload: dict[str, Any], endpoint: AgentIngressEndpoint) -> dict[str, Any]:
        view = payload.get("view") or {}
        if view.get("callback_id") != VIEW_FEEDBACK_COMMENT:
            return {}

        message_id = view.get("private_metadata") or ""
        slack_user_id = (payload.get("user") or {}).get("id", "")
        user_id = await resolve_eligible_slack_user_id(
            self.db,
            tenant_id=endpoint.tenant_id,
            slack_user_id=slack_user_id,
            endpoint=endpoint,
            identity_service=self.identity_service,
        )
        if not user_id or not message_id:
            return {}

        state_values = view.get("state", {}).get("values", {})
        comment_block = state_values.get("comment_block", {})
        comment_input = comment_block.get("comment_input", {})
        comment = (comment_input.get("value") or "").strip()

        feedback_service = MessageFeedbackService(endpoint.tenant_id, self.db)
        await feedback_service.update_comment(message_id=message_id, user_id=user_id, comment=comment or None)
        return {"response_action": "clear"}


def _extract_text_from_blocks(blocks: list[dict] | None) -> str:
    if not blocks:
        return ""
    for block in blocks:
        if block.get("type") == "section":
            text_obj = block.get("text") or {}
            if text_obj.get("text"):
                return str(text_obj["text"])
    return ""


def parse_interactivity_payload(body: str) -> dict[str, Any]:
    """Parse Slack interactivity form body."""
    from urllib.parse import parse_qs

    parsed = parse_qs(body)
    raw = parsed.get("payload", [""])[0]
    if not raw:
        return {}
    return json.loads(raw)
