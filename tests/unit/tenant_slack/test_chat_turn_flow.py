"""Unit tests for Slack committed chat turn orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import DomainException
from apps.tenant_app_service.agent_ingress.slack.chat_turn_flow import run_slack_committed_chat_turn
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.shared.schemas.user import UserDTO


def _user() -> UserDTO:
    return UserDTO(
        id=10,
        username="u",
        role="admin",
        tenant_id=1,
        tenant_name="T",
    )


def _request() -> ChatRequest:
    return ChatRequest(
        tenant_id=1,
        agent_id=-1,
        thread_id="1_10_-1_x",
        message=SimpleMessage(role="human", content="hi"),
    )


@pytest.mark.asyncio
async def test_run_slack_turn_posts_thinking_between_prepare_and_complete():
    order: list[str] = []

    async def fake_prepare(*_args, **_kwargs):
        order.append("prepare")
        return MagicMock(session_id="s1")

    async def fake_complete(*_args, **_kwargs):
        order.append("complete")
        return MagicMock(
            response=MagicMock(content="reply", message_id="m1", session_id="s1"),
        )

    async def post_thinking():
        order.append("thinking")
        return "ts-thinking"

    with (
        patch(
            "apps.tenant_app_service.agent_ingress.slack.chat_turn_flow.prepare_chat_turn_committed",
            fake_prepare,
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.chat_turn_flow.complete_chat_turn_committed",
            fake_complete,
        ),
    ):
        result = await run_slack_committed_chat_turn(
            1,
            _request(),
            _user(),
            "token",
            post_thinking_placeholder=post_thinking,
        )

    assert order == ["prepare", "thinking", "complete"]
    assert result.reply_text == "reply"
    assert result.thinking_ts == "ts-thinking"
    assert result.message_id == "m1"


@pytest.mark.asyncio
async def test_run_slack_turn_maps_domain_exception_to_reply_text():
    with patch(
        "apps.tenant_app_service.agent_ingress.slack.chat_turn_flow.prepare_chat_turn_committed",
        AsyncMock(side_effect=DomainException("denied")),
    ):
        result = await run_slack_committed_chat_turn(
            1,
            _request(),
            _user(),
            "token",
            post_thinking_placeholder=AsyncMock(return_value=None),
        )

    assert "denied" in result.reply_text.lower() or result.reply_text
