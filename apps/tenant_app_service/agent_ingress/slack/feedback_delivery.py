"""Shared Slack reply delivery with optional feedback buttons."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort
from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import SlackMarkdownPolicy
from apps.tenant_app_service.agent_ingress.slack.markdown_delivery import deliver_markdown_to_slack
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import ImageFetcher
from apps.tenant_app_service.chat.feedback_message_lookup import (
    feedback_message_id_exists,
    resolve_latest_ai_message_id_for_session,
    update_message_metadata_for_feedback,
)


async def resolve_feedback_message_id(
    db_session: AsyncSession,
    *,
    message_id: str | None,
    session_id: str | None,
    thread_id: str,
) -> str | None:
    """Resolve AI message_id from chat response or latest session message."""
    if message_id and await feedback_message_id_exists(db_session, message_id):
        return message_id
    if not session_id:
        return message_id
    resolved = await resolve_latest_ai_message_id_for_session(
        db_session,
        thread_id=thread_id,
        session_id=session_id,
    )
    return resolved or message_id


async def post_slack_reply_with_feedback(
    *,
    client: SlackClientPort,
    bot_token: str,
    channel_id: str,
    text: str,
    message_id: str | None,
    thread_ts: str | None,
    db_session: AsyncSession,
    update_ts: str | None = None,
    portal_origin: str | None = None,
    api_origin: str | None = None,
    slack_user_id: str | None = None,
    channel_type: str | None = None,
    policy: SlackMarkdownPolicy | None = None,
    image_fetcher: ImageFetcher | None = None,
    tenant_id: int | None = None,
    requester_user_id: int | None = None,
    requester_role: str | None = None,
    agent_id: int | None = None,
) -> str | None:
    """Render agent Markdown to Slack blocks and attach feedback on the last message."""
    posted_ts = await deliver_markdown_to_slack(
        client=client,
        bot_token=bot_token,
        channel_id=channel_id,
        markdown=text,
        message_id=message_id,
        thread_ts=thread_ts,
        update_ts=update_ts,
        portal_origin=portal_origin,
        api_origin=api_origin,
        slack_user_id=slack_user_id,
        channel_type=channel_type,
        policy=policy,
        image_fetcher=image_fetcher,
        db_session=db_session,
        tenant_id=tenant_id,
        requester_user_id=requester_user_id,
        requester_role=requester_role,
        agent_id=agent_id,
    )

    if message_id and posted_ts and db_session is not None:
        ingress_patch = {
            "ingress": {"platform": "slack", "channel_id": channel_id, "message_ts": posted_ts},
        }
        existing = await update_message_metadata_for_feedback(
            db_session,
            message_id=message_id,
            metadata_patch=ingress_patch,
        )
        if not existing:
            from apps.shared.utils.logger import get_logger

            get_logger(__name__).warning(
                "Slack feedback metadata: message_id=%s not found in main or run stores",
                message_id,
            )

    return posted_ts
