"""Shared Slack reply delivery with optional feedback buttons."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort
from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import SlackMarkdownPolicy
from apps.tenant_app_service.agent_ingress.slack.markdown_delivery import deliver_markdown_to_slack
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import ImageFetcher
from apps.tenant_app_service.chat.message_repository import MessageRepository


async def resolve_feedback_message_id(
    message_repo: MessageRepository,
    *,
    message_id: str | None,
    session_id: str | None,
    thread_id: str,
) -> str | None:
    """Resolve AI message_id from chat response or latest session message."""
    if message_id:
        return message_id
    if not session_id:
        return None
    ai_message = await message_repo.get_latest_ai_message_for_session(thread_id, session_id)
    return ai_message.message_id if ai_message else None


async def post_slack_reply_with_feedback(
    *,
    client: SlackClientPort,
    bot_token: str,
    channel_id: str,
    text: str,
    message_id: str | None,
    thread_ts: str | None,
    message_repo: MessageRepository,
    update_ts: str | None = None,
    portal_origin: str | None = None,
    api_origin: str | None = None,
    slack_user_id: str | None = None,
    channel_type: str | None = None,
    policy: SlackMarkdownPolicy | None = None,
    image_fetcher: ImageFetcher | None = None,
    db_session: AsyncSession | None = None,
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

    if message_id and posted_ts:
        ai_message = await message_repo.get_message_by_message_id(message_id)
        if ai_message:
            metadata = dict(ai_message.message_metadata or {})
            metadata["ingress"] = {
                "platform": "slack",
                "channel_id": channel_id,
                "message_ts": posted_ts,
            }
            await message_repo.update_message_metadata(ai_message, metadata)

    return posted_ts
