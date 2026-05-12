"""Unit test fixtures.

This file contains unit-only setup so it does not leak into integration tests.
"""

import pytest
import pytest_asyncio


def _reject_chroma_http_client(*_args, **_kwargs):
    raise RuntimeError(
        "chromadb.HttpClient was constructed in a unit test. Mock the vector "
        "backend or HttpClient; unit tests must not open a real Chroma connection."
    )


@pytest.fixture(autouse=True)
def _block_unit_test_network_clients(monkeypatch):
    """Fail fast if a unit test constructs a live Chroma HTTP client.

    chromadb.HttpClient heartbeats with httpx timeout=None, so a missed mock can
    hang the suite. Also pin sandbox URL to loopback so accidental calls fail
    fast instead of waiting on Docker DNS for sandbox-controller.
    """
    monkeypatch.setattr("chromadb.HttpClient", _reject_chroma_http_client)
    monkeypatch.setattr(
        "apps.config.EnvConfig.AGENT_SANDBOX_BASE_URL",
        "http://127.0.0.1:8090",
    )


@pytest_asyncio.fixture
async def async_db_session():
    """Provide an in-memory async database session for unit tests.

    Uses SQLite instead of PostgreSQL for fast, isolated unit tests.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from apps.shared.db.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
