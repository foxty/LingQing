"""Shared Slack reply delivery with optional feedback buttons."""

from __future__ import annotations

from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort
from apps.tenant_app_service.agent_ingress.slack.domain import split_long_text
from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import build_feedback_blocks
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
) -> str | None:
    """Post chunked Slack reply; attach feedback buttons on the final chunk."""
    chunks = [chunk for chunk in split_long_text(text) if chunk.strip()]
    if not chunks:
        return None

    posted_ts: str | None = None
    pending_update_ts = update_ts

    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        blocks = build_feedback_blocks(chunk, message_id) if is_last and message_id else None

        if pending_update_ts:
            await client.chat_update(
                bot_token=bot_token,
                channel=channel_id,
                ts=pending_update_ts,
                text=chunk,
                blocks=blocks,
            )
            posted_ts = pending_update_ts
            pending_update_ts = None
        else:
            post_result = await client.chat_post_message(
                bot_token=bot_token,
                channel=channel_id,
                text=chunk,
                thread_ts=thread_ts,
                blocks=blocks,
            )
            posted_ts = post_result.get("ts") if post_result else posted_ts

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
