"""FastAPI get_db overrides that stay on the integration savepoint connection.

Use with ``httpx.AsyncClient(ASGITransport)`` in async integration tests.
Sync ``TestClient`` runs on a different event loop and must not share the
``pg_async_db_session`` connection (see ``tests/slack/session_factory``).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.slack.session_factory import build_serializing_savepoint_sessions


async def savepoint_get_db_override(
    async_db_session: AsyncSession,
) -> tuple[async_sessionmaker[AsyncSession], Callable[[], AsyncGenerator[AsyncSession, None]]]:
    """Bind app DB access to the same connection as ``pg_async_db_session``.

    Commits inside requests release savepoints only; the outer integration
    transaction still rolls back after the test.
    """
    connection = await async_db_session.connection()
    session_factory, override_get_db, _fake_app_db_session = build_serializing_savepoint_sessions(connection)
    return session_factory, override_get_db
