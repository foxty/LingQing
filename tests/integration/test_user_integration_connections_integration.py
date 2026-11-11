"""Integration: BYOT user integration credentials over HTTP (real DB, no warehouse I/O)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import DataSource, Tenant, TenantMembership, User, UserIntegrationCredential
from apps.tenant_app_service.server import app

TEST_SECRET_KEY = "test-secret-key"


@pytest.fixture
def mock_jwt_token():
    from jose import jwt

    def _create_token(
        user_id: int,
        username: str,
        role: str,
        tenant_id: int,
        tenant_name: str,
        expires_delta: timedelta | None = None,
    ) -> str:
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
        payload = {
            "user_id": user_id,
            "sub": username,
            "role": role,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "exp": expire,
        }
        return jwt.encode(payload, TEST_SECRET_KEY, algorithm="HS256")

    return _create_token


class _FakeDbManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def test_connection(self):
        return True, "Connection successful"


@pytest_asyncio.fixture
async def byot_connections_setup(async_db_session: AsyncSession, mock_jwt_token):
    from apps.shared.db.session import get_db

    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    suffix = uuid4().hex[:8]
    async with test_session_factory() as seed_session:
        tenant = Tenant(name=f"byot_{suffix}", slug=f"byot-{suffix}", config=None)
        seed_session.add(tenant)
        await seed_session.flush()

        user = User(
            username=f"byot_member_{suffix}",
            email=f"byot_{suffix}@test.local",
            hashed_password="$2b$12$hAjROif0svlKIjI.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",
            tenant_id=tenant.id,
            role="member",
        )
        seed_session.add(user)
        await seed_session.flush()

        seed_session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, status="active"))
        await seed_session.flush()

        data_source = DataSource(
            tenant_id=tenant.id,
            owner_id=user.id,
            name=f"warehouse_{suffix}",
            type="postgres",
            managed=False,
            credential_mode="user",
            config={
                "type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "analytics",
                "readOnly": True,
            },
            description="BYOT integration",
        )
        seed_session.add(data_source)
        await seed_session.commit()

    token = mock_jwt_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )

    yield {
        "tenant_id": tenant.id,
        "user_id": user.id,
        "data_source_id": data_source.id,
        "token": token,
        "session_factory": test_session_factory,
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_warehouse_test(monkeypatch):
    def _fake_get_db_manager_for_datasource(_domain):
        return _FakeDbManager()

    monkeypatch.setattr(
        "apps.shared.infra.analytics_db.manager_factory.get_db_manager_for_datasource",
        _fake_get_db_manager_for_datasource,
    )


@pytest.mark.asyncio
async def test_connections_me_lifecycle(byot_connections_setup, mock_warehouse_test):
    client = TestClient(app)
    headers = _auth_headers(byot_connections_setup["token"])
    ds_id = byot_connections_setup["data_source_id"]

    get0 = client.get(f"/data-sources/{ds_id}/connections/me", headers=headers)
    assert get0.status_code == 200, get0.text
    assert get0.json()["status"] == "not_connected"
    assert get0.json()["secret_keys_configured"] == []

    test_only = client.post(
        f"/data-sources/{ds_id}/connections/me/test",
        headers=headers,
        json={"auth_type": "db_password", "secrets": {"username": "probe-user", "password": "probe-secret"}},
    )
    assert test_only.status_code == 200, test_only.text
    assert test_only.json()["success"] is True

    get1 = client.get(f"/data-sources/{ds_id}/connections/me", headers=headers)
    assert get1.json()["status"] == "not_connected"

    put = client.put(
        f"/data-sources/{ds_id}/connections/me",
        headers=headers,
        json={
            "auth_type": "db_password",
            "secrets": {"password": "user-secret", "username": "alice"},
            "account_label": "work",
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["status"] == "connected"
    assert body["account_label"] == "work"
    assert "password" in body["secret_keys_configured"]
    assert body["secrets_public"].get("username") == "alice"
    assert "password" not in body["secrets_public"]

    async with byot_connections_setup["session_factory"]() as session:
        row = (
            await session.execute(
                select(UserIntegrationCredential).where(
                    UserIntegrationCredential.tenant_id == byot_connections_setup["tenant_id"],
                    UserIntegrationCredential.user_id == byot_connections_setup["user_id"],
                    UserIntegrationCredential.resource_id == ds_id,
                )
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.secrets_enc.get("password", "").startswith("enc:")


@pytest.mark.asyncio
async def test_connections_me_test_without_binding_returns_integration_not_connected(
    byot_connections_setup,
):
    client = TestClient(app)
    headers = _auth_headers(byot_connections_setup["token"])
    ds_id = byot_connections_setup["data_source_id"]

    response = client.post(f"/data-sources/{ds_id}/connections/me/test", headers=headers)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body.get("code") == "INTEGRATION_NOT_CONNECTED"
