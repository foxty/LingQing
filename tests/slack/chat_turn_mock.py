"""Stub committed chat turn helpers for Slack ingress integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_ingress.slack.chat_turn_flow import (
    PostThinkingFn,
    SlackCommittedChatTurnResult,
)
from apps.tenant_app_service.agent_ingress.slack import chat_turn_runner as chat_turn_runner_module
from apps.tenant_app_service.chat.schemas import ChatRequest
from apps.tenant_app_service.chat.streaming import PreparedChatStream


async def instant_slack_chat_turn_runner(
    tenant_id: int,
    chat_request: ChatRequest,
    user_dto: UserDTO,
    access_token: str,
    *,
    post_thinking_placeholder: PostThinkingFn,
    log_label: str = "Slack chat",
) -> SlackCommittedChatTurnResult:
    """Lane A default: post thinking, skip prepare/complete (avoids savepoint lock contention)."""
    thinking_ts = await post_thinking_placeholder()
    return SlackCommittedChatTurnResult(
        reply_text="ok",
        message_id="msg_test",
        session_id="sess_test",
        thinking_ts=thinking_ts,
    )


def default_prepared_chat_stream(**overrides: Any) -> PreparedChatStream:
    fields = {
        "session_id": "sess_test",
        "agent_id": -1,
        "agent_name": "TestAgent",
        "initial_messages": [],
        "thread_title": None,
    }
    fields.update(overrides)
    return PreparedChatStream(**fields)


def default_chat_response(
    *,
    content: str = "ok",
    message_id: str = "msg_test",
    session_id: str = "sess_test",
) -> MagicMock:
    return MagicMock(
        response=MagicMock(content=content, message_id=message_id, session_id=session_id),
    )


def patch_slack_chat_turn_complete_only(monkeypatch: Any) -> None:
    """Keep real prepare/complete; stub the LangGraph invoke so turns finish without an LLM."""

    async def fake_get_agent_graph(self, agent_id, current_user):
        class _StubGraph:
            async def ainvoke(self, input_state, config):
                from langchain_core.messages import AIMessage

                messages = list(input_state.get("messages", []))
                messages.append(AIMessage(content="integration-stub-reply"))
                return {
                    "messages": messages,
                    "loop_count": 0,
                    "tool_call_counts": {},
                }

            def get_name(self) -> str:
                return "TestAgent"

        return _StubGraph(), None

    async def fake_thread_title(self, content, thread_id, session_id):
        return None

    monkeypatch.setattr(
        "apps.tenant_app_service.chat.turn_service.ChatTurnService._get_agent_graph",
        fake_get_agent_graph,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.turn_service.ChatTurnService.create_thread_title_if_1st_message",
        fake_thread_title,
    )


class StubSlackChatTurnRunner:
    """Configurable stub installed via ``patch_slack_chat_turn``."""

    def __init__(
        self,
        *,
        on_prepare: Callable[..., Awaitable[PreparedChatStream] | PreparedChatStream] | None = None,
        on_complete: Callable[..., Awaitable[MagicMock] | MagicMock] | None = None,
    ) -> None:
        self._on_prepare = on_prepare
        self._on_complete = on_complete

    async def __call__(
        self,
        tenant_id: int,
        chat_request: ChatRequest,
        user_dto: UserDTO,
        access_token: str,
        *,
        post_thinking_placeholder: PostThinkingFn,
        log_label: str = "Slack chat",
    ) -> SlackCommittedChatTurnResult:
        if self._on_prepare is not None:
            result = self._on_prepare(tenant_id, chat_request, user_dto, log_label=log_label)
            if isinstance(result, PreparedChatStream):
                prepared = result
            else:
                prepared = await result
        else:
            prepared = default_prepared_chat_stream()

        thinking_ts = await post_thinking_placeholder()

        if self._on_complete is not None:
            try:
                result = self._on_complete(tenant_id, chat_request, user_dto, prepared, log_label=log_label)
            except TypeError:
                result = self._on_complete(None, chat_request, user_dto, prepared, log_label=log_label)
            if isinstance(result, MagicMock):
                response = result
            else:
                response = await result
            content = response.response.content
            reply_text = content if isinstance(content, str) else str(content)
            return SlackCommittedChatTurnResult(
                reply_text=reply_text,
                message_id=response.response.message_id,
                session_id=response.response.session_id,
                thinking_ts=thinking_ts,
            )

        return SlackCommittedChatTurnResult(
            reply_text="ok",
            message_id="msg_test",
            session_id="sess_test",
            thinking_ts=thinking_ts,
        )


def patch_slack_chat_turn(
    *,
    on_complete: Callable[..., Awaitable[MagicMock] | MagicMock] | None = None,
    on_prepare: Callable[..., Awaitable[PreparedChatStream] | PreparedChatStream] | None = None,
) -> None:
    """Install a stub chat-turn runner (counting invocations or skipping DB admission)."""
    chat_turn_runner_module.set_slack_chat_turn_runner(
        StubSlackChatTurnRunner(on_prepare=on_prepare, on_complete=on_complete)
    )
