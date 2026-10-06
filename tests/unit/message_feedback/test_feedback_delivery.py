"""Tests for shared Slack feedback delivery helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.agent_ingress.slack.feedback_delivery import (
    post_slack_reply_with_feedback,
    resolve_feedback_message_id,
)


@pytest.mark.asyncio
async def test_resolve_feedback_message_id_from_session():
    message_repo = MagicMock()
    ai_message = MagicMock(message_id="msg_from_session")
    message_repo.get_latest_ai_message_for_session = AsyncMock(return_value=ai_message)

    result = await resolve_feedback_message_id(
        message_repo,
        message_id=None,
        session_id="session_1",
        thread_id="thread_1",
    )

    assert result == "msg_from_session"


@pytest.mark.asyncio
async def test_post_slack_reply_with_feedback_updates_thinking_message():
    client = MagicMock()
    client.chat_update = AsyncMock(return_value={"ok": True})
    message_repo = MagicMock()
    message_repo.get_message_by_message_id = AsyncMock(return_value=None)

    posted_ts = await post_slack_reply_with_feedback(
        client=client,
        bot_token="token",
        channel_id="C1",
        text="Hello world",
        message_id=None,
        thread_ts="1.0",
        message_repo=message_repo,
        update_ts="1.1",
    )

    assert posted_ts == "1.1"
    client.chat_update.assert_awaited_once()
    client.chat_post_message.assert_not_called()
