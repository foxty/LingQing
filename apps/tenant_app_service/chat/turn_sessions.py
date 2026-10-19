"""Chat turn execution across short DB sessions.

``ChatTurnService`` is bound to one ``AsyncSession``. Prepare (lock + persist) and
agent invoke must not share a session that stays open for the LLM/SSE wait.
Committed session boundaries for HTTP, Slack, streaming, and headless turns.
Channel-specific steps (e.g. Slack thinking) live in ingress use-case modules.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.session import app_db_session
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse
from apps.tenant_app_service.chat.streaming import PreparedChatStream

if TYPE_CHECKING:
    from apps.tenant_app_service.chat.turn_service import ChatTurnService


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
    """Alias for ``with_chat_turn_service`` (legacy name)."""
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
    """Yield SSE for a prepared stream turn (agent uses its own DB sessions)."""
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    async with app_db_session() as db:
        service = ChatTurnService(tenant_id, db)
    async for item in service.iter_prepared_chat_stream(
        request,
        current_user,
        prepared,
        access_token=access_token,
    ):
        yield item


async def stream_chat_turn_events(
    tenant_id: int,
    request: ChatRequest,
    current_user: UserDTO,
    access_token: str | None = None,
) -> AsyncIterator[str]:
    """Prepare in one session, stream in another (HTTP SSE)."""
    if request.tenant_id != tenant_id:
        raise AuthorizationError(
            f"Tenant mismatch: request tenant {request.tenant_id} != service tenant {tenant_id}"
        )

    prepared = await prepare_chat_stream_committed(
        tenant_id,
        request,
        current_user,
        access_token=access_token,
    )
    async for item in iter_prepared_chat_stream_committed(
        tenant_id,
        request,
        current_user,
        prepared,
        access_token=access_token,
    ):
        yield item
