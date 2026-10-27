"""Shared LangGraph checkpointer (Postgres in production, memory in tests)."""

from __future__ import annotations

from typing import Any

from apps.config import EnvConfig
from apps.shared.db.url import build_postgres_psycopg_url
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_checkpointer: Any | None = None
_checkpointer_owner: Any | None = None


def get_langgraph_checkpointer() -> Any | None:
    """Return the process-wide checkpointer, or None before startup."""
    return _checkpointer


async def init_langgraph_checkpointer() -> Any:
    """Create and store the LangGraph checkpointer (call from app lifespan)."""
    global _checkpointer, _checkpointer_owner
    if _checkpointer is not None:
        return _checkpointer

    if EnvConfig.LANGGRAPH_CHECKPOINTER_MEMORY:
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        logger.info("LangGraph checkpointer: in-memory MemorySaver")
        return _checkpointer

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn_string = build_postgres_psycopg_url(
        user=EnvConfig.TENANT_APP_DB_USER,
        password=EnvConfig.TENANT_APP_DB_PASSWORD,
        host=EnvConfig.TENANT_APP_DB_HOST,
        port=EnvConfig.TENANT_APP_DB_PORT,
        db_name=EnvConfig.TENANT_APP_DB_NAME,
        ssl_mode=EnvConfig.TENANT_APP_DB_SSL_MODE or None,
    )
    owner = AsyncPostgresSaver.from_conn_string(conn_string)
    _checkpointer = await owner.__aenter__()
    _checkpointer_owner = owner
    await _checkpointer.setup()
    logger.info("LangGraph checkpointer: AsyncPostgresSaver initialized")
    return _checkpointer


async def shutdown_langgraph_checkpointer() -> None:
    """Release checkpointer resources on app shutdown."""
    global _checkpointer, _checkpointer_owner
    if _checkpointer_owner is not None:
        await _checkpointer_owner.__aexit__(None, None, None)
    _checkpointer = None
    _checkpointer_owner = None
