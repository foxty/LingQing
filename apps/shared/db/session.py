"""Database session management for multi-tenant architecture.

Supports PostgreSQL (main + per-tenant databases).

Architecture:
- Main DB: Stores platform metadata (tenants, users, agents, data_sources)
  - PostgreSQL
  - Single engine, shared across requests
- Tenant DBs: One per tenant for managed analytics data
  - PostgreSQL only
  - Lazily created and cached per tenant
  - Credentials stored in DataSource.config, not environment
"""

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.config import EnvConfig
from apps.shared.db.url import build_postgres_asyncpg_url
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def build_main_db_url() -> str:
    """Build main database URL based on configuration.

    Returns:
        Connection URL for main database (PostgreSQL)
    """
    logger.info(f"Building main DB URL for user: {EnvConfig.TENANT_APP_DB_USER}")
    return build_postgres_asyncpg_url(
        user=EnvConfig.TENANT_APP_DB_USER,
        password=EnvConfig.TENANT_APP_DB_PASSWORD,
        host=EnvConfig.TENANT_APP_DB_HOST,
        port=EnvConfig.TENANT_APP_DB_PORT,
        db_name=EnvConfig.TENANT_APP_DB_NAME,
        ssl_mode=EnvConfig.TENANT_APP_DB_SSL_MODE or None,
    )


# ========== App Database Setup ==========

# Create async app db engine for main database
app_db_engine = create_async_engine(
    url=build_main_db_url(),
    echo=False,  # Set to True for SQL debugging
    future=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    connect_args={
        "timeout": 10,  # Connection timeout in seconds
        "command_timeout": 30,  # Query execution timeout in seconds
    },
)

# Session factory for main database (internal — use db_session() or get_app_db() instead)
_AsyncSessionLocal = async_sessionmaker(
    app_db_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def app_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for standalone database sessions.

    Use this wherever a session must be created outside of a FastAPI request
    (background tasks, CLI scripts, scheduled jobs, agent tools, etc.).
    Commits on clean exit, rolls back on any exception.

    Usage::

        async with app_db_session() as db:
            await repo.create(entity)   # flush only inside repo
        # commit happens here automatically

    Yields:
        AsyncSession: Database session with auto-commit/rollback
    """
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_app_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get main database session.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_app_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    Yields:
        AsyncSession: Main database session
    """
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ========== Tenant Database Factory (for analytics) ==========
# Note: Tenant credentials are stored in DataSource.config, not environment


@lru_cache(maxsize=EnvConfig.TENANT_POOL_CACHE_SIZE)
def _get_tenant_engine(tenant_id: int, host: str, port: int, user: str, password: str, db_name: str):
    """Create and cache tenant database engine.

    This is cached to reuse connections across requests for the same tenant.

    Args:
        tenant_id: Tenant ID (for logging)
        host: Database host
        port: Database port
        user: Database user
        password: Database password
        db_name: Database name

    Returns:
        Async SQLAlchemy engine for tenant database
    """
    url = build_postgres_asyncpg_url(
        user=user,
        password=password,
        host=host,
        port=port,
        db_name=db_name,
        ssl_mode=EnvConfig.TENANT_APP_DB_SSL_MODE or None,
    )

    engine = create_async_engine(
        url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=EnvConfig.TENANT_POOL_SIZE,
        max_overflow=EnvConfig.TENANT_POOL_MAX_OVERFLOW,
        pool_recycle=3600,
        connect_args={
            "timeout": 10,  # Connection timeout in seconds
            "command_timeout": 30,  # Query execution timeout in seconds
        },
    )

    logger.debug(f"Created cached engine for tenant {tenant_id}")
    return engine


async def get_tenant_db(
    tenant_id: int, host: str, port: int, user: str, password: str, db_name: str
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get tenant-specific database session.

    Credentials come from DataSource configuration, not environment.
    Engines are cached per unique (host, port, user, db_name) combination.

    Args:
        tenant_id: Tenant ID
        host: Database host
        port: Database port
        user: Database user
        password: Database password
        db_name: Database name

    Yields:
        AsyncSession: Tenant database session
    """
    engine = _get_tenant_engine(tenant_id, host, port, user, password, db_name)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ========== Backward Compatibility ==========


# Keep old name for backward compatibility
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Backward compatibility alias for get_main_db."""
    async for session in get_app_db():
        yield session
