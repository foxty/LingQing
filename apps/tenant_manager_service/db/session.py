"""Database session management for tenant manager service."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.config import EnvConfig


def build_tenant_manager_db_url() -> str:
    """Build tenant manager database URL.

    Falls back to TENANT_APP_DB_* when dedicated tenant manager DB envs are not configured.
    """
    host = EnvConfig.TENANT_MANAGER_DB_HOST
    port = EnvConfig.TENANT_MANAGER_DB_PORT
    user = EnvConfig.TENANT_MANAGER_DB_USER
    password = EnvConfig.TENANT_MANAGER_DB_PASSWORD
    db_name = EnvConfig.TENANT_MANAGER_DB_NAME

    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
    ssl_mode = getattr(EnvConfig, "TENANT_MANAGER_DB_SSL_MODE", "") or EnvConfig.TENANT_APP_DB_SSL_MODE
    if ssl_mode:
        url += f"?ssl={ssl_mode}"
    return url


tenant_manager_engine = create_async_engine(
    url=build_tenant_manager_db_url(),
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    connect_args={
        "timeout": 10,
        "command_timeout": 30,
    },
)

TenantManagerSessionLocal = async_sessionmaker(
    tenant_manager_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_tenant_manager_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get tenant manager database session."""
    async with TenantManagerSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
