"""Database session helper for agent tools."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.session import app_db_session


@asynccontextmanager
async def agent_tool_db_session(config: RunnableConfig | None) -> AsyncIterator[AsyncSession]:
    """Yield the agent runtime session when available, else a standalone session.

    Scheduled/headless runs create thread rows in the runtime session before tools
    execute. Tools that open a new session cannot see those uncommitted rows.
    """
    runtime_session = None
    if config:
        runtime_session = config.get("configurable", {}).get("db_session")
    if runtime_session is not None:
        yield runtime_session
        return
    async with app_db_session() as session:
        yield session
