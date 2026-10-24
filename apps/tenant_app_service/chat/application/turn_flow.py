"""Committed chat turn flows (application layer).

**Role:** Orchestrate use cases that span multiple DB transactions and optional SSE
transport. This module owns *when* sessions open/close and *how* streaming is wired;
it does not embed turn business rules (those live on ``ChatTurnService`` and domain).

**Callers:** HTTP router, Slack ingress, headless runners — not unit tests that
exercise a single prepare/invoke phase (those construct ``ChatTurnService`` with a
mock ``AsyncSession`` instead).

**Must not:** SQL, repository calls, LangGraph invoke, or inline domain invariants.

Streaming HTTP:
  1. ``prepare_chat_stream_committed`` — short DB session, commit, ``PreparedChatStream``
  2. ``iter_prepared_chat_stream_committed`` — SSE only; agent uses its own sessions
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.session import app_db_session
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse
from apps.tenant_app_service.chat.streaming import (
    PreparedChatStream,
    iter_sse_from_event_queue,
    prepared_stream_opening_sse,
)

if TYPE_CHECKING:
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

logger = get_logger(__name__)


async def with_chat_turn_service(
    tenant_id: int,
    operation: Callable[[ChatTurnService], Awaitable],
):
    """Run ``operation(service)`` with a committed short-lived DB session."""
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    async with app_db_session() as db:
        service = ChatTurnService(tenant_id, db)
        return await operation(service)


async def with_chat_service(tenant_id: int, operation: Callable[..., Awaitable]):
    """Alias for ``with_chat_turn_service``."""
    return await with_chat_turn_service(tenant_id, operation)


async def prepare_chat_turn_committed(
    tenant_id: int,
    request: ChatRequest,
    current_user: UserDTO,
    access_token: str | None = None,
    *,
    log_label: str = "Chat",
) -> PreparedChatStream:
    """Admission lock + persist human message; commit before agent work."""

    async def _prepare(service: ChatTurnService) -> PreparedChatStream:
        return await service.prepare_chat_turn(
            request,
            current_user,
            access_token=access_token,
            log_label=log_label,
        )

    return await with_chat_service(tenant_id, _prepare)


async def complete_chat_turn_committed(
    tenant_id: int,
    request: ChatRequest,
    current_user: UserDTO,
    prepared: PreparedChatStream,
    access_token: str | None = None,
) -> ChatResponse:
    """Invoke agent for a turn already prepared in a prior session."""

    async def _complete(service: ChatTurnService) -> ChatResponse:
        return await service.complete_chat_turn(
            request,
            current_user,
            prepared,
            access_token=access_token,
        )

    return await with_chat_service(tenant_id, _complete)


async def run_non_stream_chat_turn(
    tenant_id: int,
    request: ChatRequest,
    current_user: UserDTO,
    access_token: str | None = None,
) -> ChatResponse:
    """Prepare in one session, run agent in another (non-streaming)."""
    if request.tenant_id != tenant_id:
        raise AuthorizationError(
            f"Tenant mismatch: request tenant {request.tenant_id} != service tenant {tenant_id}"
        )

    prepared = await prepare_chat_turn_committed(
        tenant_id,
        request,
        current_user,
        access_token=access_token,
        log_label="Chat",
    )
    return await complete_chat_turn_committed(
        tenant_id,
        request,
        current_user,
        prepared,
        access_token=access_token,
    )


async def prepare_chat_stream_committed(
    tenant_id: int,
    request: ChatRequest,
    current_user: UserDTO,
    access_token: str | None = None,
) -> PreparedChatStream:
    """Admission + persist for SSE; commit before streaming."""

    async def _prepare(service: ChatTurnService) -> PreparedChatStream:
        return await service.prepare_chat_stream(
            request,
            current_user,
            access_token=access_token,
        )

    return await with_chat_service(tenant_id, _prepare)


async def iter_prepared_chat_stream_committed(
    tenant_id: int,
    request: ChatRequest,
    current_user: UserDTO,
    prepared: PreparedChatStream,
    access_token: str | None = None,
) -> AsyncIterator[str]:
    """Yield SSE for a prepared stream turn without pinning a DB session for the wait."""
    event_queue: asyncio.Queue[str | None] = asyncio.Queue()

    for line in prepared_stream_opening_sse(prepared):
        yield line

    async def _background() -> None:
        async def _run(service: ChatTurnService) -> None:
            await service.run_agent_and_emit_prepared(
                event_queue=event_queue,
                request=request,
                current_user=current_user,
                prepared=prepared,
                access_token=access_token,
            )

        await with_chat_service(tenant_id, _run)

    asyncio.create_task(_background())

    def _log_disconnect(session_id: str) -> None:
        logger.info(
            "SSE client disconnected for session %s; agent continues in background",
            session_id,
        )

    async for line in iter_sse_from_event_queue(
        event_queue,
        session_id=prepared.session_id,
        on_client_disconnect=_log_disconnect,
    ):
        yield line
