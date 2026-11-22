"""Shared fixtures for analytics DB integration tests (testcontainers + psql provisioning)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.session import get_db
from apps.tenant_app_service.server import app
from tests.integration.conftest import TEST_SECRET_KEY
from tests.integration.helpers.analytics_provision import (
    parse_pg_container_coords,
    provision_standalone_postgres_database,
    provision_tenant_with_managed_analytics,
    teardown_standalone_postgres_database,
)
from tests.slack.session_factory import build_serializing_savepoint_sessions

SPECIAL_ROLE_PASSWORD = "integ_p&ss%40word_ab12"
BYOT_WAREHOUSE_PASSWORD = "byot_wh_p&ss%40word_cd34"
METADATA_SYNC_PASSWORD = "sync_p&ss%40word_ef56"


@pytest.fixture
def pg_coords(pg_container: str):
    return parse_pg_container_coords(pg_container)


@pytest_asyncio.fixture
async def provisioned_analytics_stack(async_db_session: AsyncSession, pg_container: str, monkeypatch):
    """Tenant + provisioned analytics DB + managed DataSource; tears down Postgres objects after."""
    host, port = parse_pg_container_coords(pg_container)
    stack = await provision_tenant_with_managed_analytics(
        async_db_session,
        monkeypatch=monkeypatch,
        role_password=SPECIAL_ROLE_PASSWORD,
        pg_host=host,
        pg_port=port,
    )
    try:
        yield stack
    finally:
        try:
            await stack["provisioning"].unprovision_analytics_db(stack["tenant_id"])
        except Exception:
            pass


@pytest_asyncio.fixture
async def standalone_warehouse_db(pg_coords, monkeypatch):
    """Non-tenant analytics database + role (external / BYOT warehouse) on testcontainers Postgres."""
    host, port = pg_coords
    stack = await provision_standalone_postgres_database(
        monkeypatch=monkeypatch,
        pg_host=host,
        pg_port=port,
        role_password=BYOT_WAREHOUSE_PASSWORD,
    )
    try:
        yield stack
    finally:
        try:
            await teardown_standalone_postgres_database(stack)
        except Exception:
            pass


@pytest.fixture
def analytics_jwt_encoder():
    from jose import jwt

    def _encode(*, user_id: int, username: str, role: str, tenant_id: int, tenant_name: str) -> str:
        payload = {
            "user_id": user_id,
            "sub": username,
            "role": role,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        return jwt.encode(payload, TEST_SECRET_KEY, algorithm="HS256")

    return _encode


@pytest_asyncio.fixture
async def analytics_http_client(async_db_session: AsyncSession, provisioned_analytics_stack, analytics_jwt_encoder):
    """httpx ASGI client on the same savepoint connection as the provisioned stack."""
    connection = await async_db_session.connection()
    _, override_get_db, _ = build_serializing_savepoint_sessions(connection)
    app.dependency_overrides[get_db] = override_get_db

    stack = provisioned_analytics_stack
    token = analytics_jwt_encoder(
        user_id=stack["user"].id,
        username=stack["user"].username,
        role=stack["user"].role,
        tenant_id=stack["tenant_id"],
        tenant_name=stack["tenant_name"],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "stack": stack,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    app.dependency_overrides.clear()