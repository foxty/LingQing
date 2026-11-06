"""Slack ingress: committed chat turn (prepare → thinking → complete)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from apps.shared.core.exceptions import DomainException, ThreadBusyError
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.messages import (
    SlackMessageKey,
    slack_chat_error_message,
    slack_user_message,
)
from apps.tenant_app_service.chat.application import (
    complete_chat_turn_committed,
    prepare_chat_turn_committed,
)
from apps.tenant_app_service.chat.schemas import ChatRequest
from apps.tenant_app_service.chat.streaming import PreparedChatStream

logger = get_logger(__name__)

PostThinkingFn = Callable[[PreparedChatStream], Awaitable[str | None]]


@dataclass(frozen=True)
class SlackCommittedChatTurnResult:
    """Outcome of a Slack chat turn after prepare/complete (or mapped failure)."""

    reply_text: str
    message_id: str | None = None
    session_id: str | None = None
    thinking_ts: str | None = None
    run_id: str | None = None


async def run_slack_committed_chat_turn(
    tenant_id: int,
    chat_request: ChatRequest,
    user_dto: UserDTO,
    access_token: str,
    *,
    post_thinking_placeholder: PostThinkingFn,
    log_label: str = "Slack chat",
) -> SlackCommittedChatTurnResult:
    """Prepare (committed), post Slack thinking placeholder, complete (committed).

    ``ThreadBusyError`` is re-raised for the caller to send an ephemeral.
    Other failures return a user-facing ``reply_text`` without raising.
    """
    message_id: str | None = None
    session_id: str | None = None
    thinking_ts: str | None = None
    run_id: str | None = None
    try:
        prepared = await prepare_chat_turn_committed(
            tenant_id,
            chat_request,
            user_dto,
            access_token=access_token,
            log_label=log_label,
        )
        thinking_ts = await post_thinking_placeholder(prepared)
        from apps.tenant_app_service.chat.agent_run_execution_registry import register, unregister

        run_id = prepared.run_id
        current = asyncio.current_task()
        if run_id and current is not None:
            register(run_id, current)
        try:
            response = await complete_chat_turn_committed(
                tenant_id,
                chat_request,
                user_dto,
                prepared,
                access_token=access_token,
            )
        finally:
            if run_id:
                unregister(run_id)
        message_id = response.response.message_id
        session_id = response.response.session_id
        content = response.response.content
        reply_text = content if isinstance(content, str) else str(content)
        return SlackCommittedChatTurnResult(
            reply_text=reply_text,
            message_id=message_id,
            session_id=session_id,
            thinking_ts=thinking_ts,
            run_id=run_id,
        )
    except asyncio.CancelledError:
        logger.info("Slack chat turn task cancelled tenant=%s run_id=%s", tenant_id, run_id)
        return SlackCommittedChatTurnResult(
            reply_text=slack_user_message(SlackMessageKey.REQUEST_CANCELED),
            thinking_ts=thinking_ts,
            run_id=run_id,
        )
    except ThreadBusyError:
        raise
    except DomainException as exc:
        logger.warning(
            "Slack chat failed for tenant %s user %s: %s",
            tenant_id,
            user_dto.id,
            exc.message,
        )
        return SlackCommittedChatTurnResult(
            reply_text=slack_chat_error_message(exc),
            thinking_ts=thinking_ts,
            run_id=run_id,
        )
    except Exception:
        logger.exception("Slack chat invocation failed for tenant %s user %s", tenant_id, user_dto.id)
        return SlackCommittedChatTurnResult(
            reply_text=slack_user_message(SlackMessageKey.CHAT_GENERIC_FAILURE),
            thinking_ts=thinking_ts,
            run_id=run_id,
        )
