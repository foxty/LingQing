"""Slack ingress chat-turn runner (production default + test override hook)."""

from __future__ import annotations

from typing import Protocol

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_ingress.slack.chat_turn_flow import (
    PostThinkingFn,
    SlackCommittedChatTurnResult,
    run_slack_committed_chat_turn,
)
from apps.tenant_app_service.chat.schemas import ChatRequest


class SlackChatTurnRunner(Protocol):
    async def __call__(
        self,
        tenant_id: int,
        chat_request: ChatRequest,
        user_dto: UserDTO,
        access_token: str,
        *,
        post_thinking_placeholder: PostThinkingFn,
        log_label: str = "Slack chat",
    ) -> SlackCommittedChatTurnResult: ...


_runner_override: SlackChatTurnRunner | None = None


def get_slack_chat_turn_runner() -> SlackChatTurnRunner:
    if _runner_override is not None:
        return _runner_override
    return run_slack_committed_chat_turn


def set_slack_chat_turn_runner(runner: SlackChatTurnRunner | None) -> None:
    global _runner_override
    _runner_override = runner


def reset_slack_chat_turn_runner() -> None:
    set_slack_chat_turn_runner(None)


async def run_slack_chat_turn(
    tenant_id: int,
    chat_request: ChatRequest,
    user_dto: UserDTO,
    access_token: str,
    *,
    post_thinking_placeholder: PostThinkingFn,
    log_label: str = "Slack chat",
) -> SlackCommittedChatTurnResult:
    runner = get_slack_chat_turn_runner()
    return await runner(
        tenant_id,
        chat_request,
        user_dto,
        access_token,
        post_thinking_placeholder=post_thinking_placeholder,
        log_label=log_label,
    )
