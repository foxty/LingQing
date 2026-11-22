"""BYOT data-source connections against a real warehouse (URL-encoded passwords, no DB mocks)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import DataSource, Tenant, TenantMembership, User
from apps.shared.db.session import get_db
from apps.tenant_app_service.server import app
from tests.integration.analytics_db.conftest import BYOT_WAREHOUSE_PASSWORD
from tests.slack.session_factory import build_serializing_savepoint_sessions


@pytest_asyncio.fixture
async def byot_real_warehouse_client(
    async_db_session: AsyncSession,
    standalone_warehouse_db,
    analytics_jwt_encoder,
):
    conn = standalone_warehouse_db["connection"]
    suffix = standalone_warehouse_db["suffix"]

    tenant = Tenant(name=f"byot_wh_{suffix}", slug=f"byot-wh-{suffix}", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username=f"byot_member_{suffix}",
        email=f"byot_member_{suffix}@test.local",
        hashed_password="$2b$12$hAjROif0svlKIj.I.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",
        tenant_id=tenant.id,
        role="member",
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.flush()
    async_db_session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, status="active"))
    await async_db_session.flush()

    data_source = DataSource(
        tenant_id=tenant.id,
        owner_id=user.id,
        name=f"warehouse_{suffix}",
        type="postgres",
        managed=False,
        credential_mode="user",
        config={
            "host": conn.host,
            "port": conn.port,
            "database": conn.database,
            "readOnly": True,
        },
        description="BYOT real warehouse integration",
    )
    async_db_session.add(data_source)
    await async_db_session.flush()

    connection = await async_db_session.connection()
    _, override_get_db, _ = build_serializing_savepoint_sessions(connection)
    app.dependency_overrides[get_db] = override_get_db

    token = analytics_jwt_encoder(
        user_id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "headers": {"Authorization": f"Bearer {token}"},
            "data_source_id": data_source.id,
            "warehouse_username": conn.username,
            "warehouse_password": conn.password,
        }
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_byot_connection_test_hits_real_warehouse_with_encoded_password(byot_real_warehouse_client):
    client = byot_real_warehouse_client["client"]
    headers = byot_real_warehouse_client["headers"]
    ds_id = byot_real_warehouse_client["data_source_id"]

    response = await client.post(
        f"/data-sources/{ds_id}/connections/me/test",
        headers=headers,
        json={
            "auth_type": "db_password",
            "secrets": {
                "username": byot_real_warehouse_client["warehouse_username"],
                "password": byot_real_warehouse_client["warehouse_password"],
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert byot_real_warehouse_client["warehouse_password"] == BYOT_WAREHOUSE_PASSWORD


@pytest.mark.asyncio
async def test_byot_bind_and_test_persisted_credentials(byot_real_warehouse_client):
    client = byot_real_warehouse_client["client"]
    headers = byot_real_warehouse_client["headers"]
    ds_id = byot_real_warehouse_client["data_source_id"]

    put = await client.put(
        f"/data-sources/{ds_id}/connections/me",
        headers=headers,
        json={
            "auth_type": "db_password",
            "secrets": {
                "username": byot_real_warehouse_client["warehouse_username"],
                "password": byot_real_warehouse_client["warehouse_password"],
            },
            "account_label": f"work_{uuid4().hex[:6]}",
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["status"] == "connected"

    test_bound = await client.post(
        f"/data-sources/{ds_id}/connections/me/test",
        headers=headers,
    )
    assert test_bound.status_code == 200, test_bound.text
    assert test_bound.json()["success"] is True