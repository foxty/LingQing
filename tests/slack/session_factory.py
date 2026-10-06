"""Savepoint session helpers for Slack integration tests.

Slack ingress runs chat in a background ``app_db_session`` while the HTTP
request and ChatService session-end work may open additional sessions.
PostgreSQL savepoints are per-connection; concurrent sessions on one connection
corrupt the stack. Serialize access with a lock while keeping savepoint rollback
from ``pg_async_db_session``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_serializing_savepoint_sessions(
    connection,
) -> tuple[
    async_sessionmaker[AsyncSession],
    Callable[[], AsyncGenerator[AsyncSession, None]],
    Callable[[], AsyncGenerator[AsyncSession, None]],
]:
    """Build session factory + get_db/app_db_session overrides for Slack tests."""
    lock = asyncio.Lock()
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with lock:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    await session.close()

    @asynccontextmanager
    async def fake_app_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with lock:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

    return session_factory, override_get_db, fake_app_db_session
