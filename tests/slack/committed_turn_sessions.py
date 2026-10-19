"""Wire chat turn_sessions to real commits on the Slack integration DB."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def patch_committed_turn_sessions(monkeypatch: Any, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Use the Slack test session factory for prepare/complete (visible commits).

    Safe for sequential Slack turns only (factory is savepoint-bound to one PG connection).
    """

    monkeypatch.setattr(
        "apps.tenant_app_service.chat.turn_sessions.app_db_session",
        _committed_context_manager(session_factory),
    )


def _committed_context_manager(session_factory: async_sessionmaker[AsyncSession]):
    @asynccontextmanager
    async def _committed_app_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _committed_app_db_session
