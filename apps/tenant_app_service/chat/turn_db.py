"""Short-lived DB sessions for agent graph orchestration (release pool during LLM I/O)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from apps.shared.db.session import app_db_session

T = TypeVar("T")


@asynccontextmanager
async def turn_service_session(tenant_id: int):
    """One commit/rollback scope for a single orchestration step."""
    from apps.tenant_app_service.chat.application.turn import ChatTurnService

    async with app_db_session() as db:
        yield ChatTurnService(tenant_id, db)


async def with_turn_service(tenant_id: int, operation: Callable[..., Awaitable[T]], /, *args, **kwargs) -> T:
    async with turn_service_session(tenant_id) as service:
        return await operation(service, *args, **kwargs)
