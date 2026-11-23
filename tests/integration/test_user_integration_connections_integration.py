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
        "tenant_name": tenant.name,
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
    assert get0.json()["masked_fields"] == []
    assert get0.json()["secrets"] == {}

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
    assert "secrets.password" in body["masked_fields"]
    assert body["secrets"].get("username") == "alice"
    assert "password" in body["secrets"]
    assert "alice" not in body["secrets"]["password"]
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


@pytest.mark.asyncio
async def test_admin_provisions_user_connection(byot_connections_setup, mock_jwt_token, mock_warehouse_test):
    client = TestClient(app)
    member_headers = _auth_headers(byot_connections_setup["token"])
    ds_id = byot_connections_setup["data_source_id"]
    member_id = byot_connections_setup["user_id"]

    async with byot_connections_setup["session_factory"]() as session:
        admin = User(
            username="byot_admin",
            email="admin@test.local",
            hashed_password="$2b$12$hAjROif0svlKIjI.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",
            tenant_id=byot_connections_setup["tenant_id"],
            role="admin",
        )
        session.add(admin)
        await session.flush()
        session.add(
            TenantMembership(
                tenant_id=byot_connections_setup["tenant_id"],
                user_id=admin.id,
                status="active",
            )
        )
        await session.commit()
        admin_id = admin.id

    admin_token = mock_jwt_token(
        user_id=admin_id,
        username="byot_admin",
        role="admin",
        tenant_id=byot_connections_setup["tenant_id"],
        tenant_name=byot_connections_setup["tenant_name"],
    )
    admin_headers = _auth_headers(admin_token)

    put = client.put(
        f"/data-sources/{ds_id}/connections/users/{member_id}",
        headers=admin_headers,
        json={
            "auth_type": "db_password",
            "secrets": {"password": "admin-set-secret", "username": "bob"},
            "account_label": "it",
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["status"] == "connected"
    assert body["account_label"] == "it"

    member_get = client.get(f"/data-sources/{ds_id}/connections/me", headers=member_headers)
    assert member_get.status_code == 200
    assert member_get.json()["status"] == "connected"

    listed = client.get(f"/data-sources/{ds_id}/connections", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert any(item["user_id"] == member_id and item["status"] == "connected" for item in items)
    assert any(item.get("provisioned_by_user_id") == admin_id for item in items)


@pytest.mark.asyncio
async def test_admin_provision_rejects_user_not_in_tenant(byot_connections_setup, mock_jwt_token):
    client = TestClient(app)
    ds_id = byot_connections_setup["data_source_id"]

    async with byot_connections_setup["session_factory"]() as session:
        admin = User(
            username="byot_admin2",
            email="admin2@test.local",
            hashed_password="$2b$12$hAjROif0svlKIjI.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",
            tenant_id=byot_connections_setup["tenant_id"],
            role="admin",
        )
        session.add(admin)
        await session.flush()
        session.add(
            TenantMembership(
                tenant_id=byot_connections_setup["tenant_id"],
                user_id=admin.id,
                status="active",
            )
        )
        await session.commit()
        admin_id = admin.id

    admin_token = mock_jwt_token(
        user_id=admin_id,
        username="byot_admin2",
        role="admin",
        tenant_id=byot_connections_setup["tenant_id"],
        tenant_name=byot_connections_setup["tenant_name"],
    )
    put = client.put(
        f"/data-sources/{ds_id}/connections/users/{999_999}",
        headers=_auth_headers(admin_token),
        json={
            "auth_type": "db_password",
            "secrets": {"password": "x", "username": "bob"},
        },
    )
    assert put.status_code == 404, put.text
