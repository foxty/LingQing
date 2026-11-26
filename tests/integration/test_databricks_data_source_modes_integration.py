"""Integration: Databricks data sources — shared, BYOT PAT, and BYOT OAuth over HTTP."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import Tenant, TenantMembership, User
from apps.shared.db.session import get_db
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
    prepare_user_oauth_config_for_storage,
)
from apps.shared.utils.field_cipher import FieldCipher
from apps.tenant_app_service.server import app
from tests.helpers.data_source_fixtures import seed_data_source_owner_policies
from tests.integration.conftest import TEST_SECRET_KEY

DBX_HOST = "adb-example.azuredatabricks.net"
DBX_WAREHOUSE = {"http_path": "/sql/1.0/warehouses/synthetic"}


class _FakeDbManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def test_connection(self):
        return True, "Connection successful"


def _jwt_token(
    *,
    user_id: int,
    username: str,
    role: str,
    tenant_id: int,
    tenant_name: str,
) -> str:
    from jose import jwt

    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    return jwt.encode(
        {
            "user_id": user_id,
            "sub": username,
            "role": role,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "exp": expire,
        },
        TEST_SECRET_KEY,
        algorithm="HS256",
    )


def _shared_databricks_config() -> dict:
    return {
        "host": DBX_HOST,
        "extra_params": dict(DBX_WAREHOUSE),
        "password": "dapi-synthetic-shared-pat",
    }


def _byot_pat_template_config() -> dict:
    return {
        "host": DBX_HOST,
        "extra_params": dict(DBX_WAREHOUSE),
        "user_credential_auth_type": "pat",
    }


def _byot_oauth_template_config(*, cipher: FieldCipher | None = None) -> dict:
    auth, token = databricks_oidc_urls(DBX_HOST)
    raw = {
        "host": DBX_HOST,
        "extra_params": dict(DBX_WAREHOUSE),
        "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
        USER_OAUTH_CONFIG_KEY: {
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "authorize_url": auth,
            "token_url": token,
            "redirect_uri": "https://api.example.test/integrations/oauth/callback",
            "scopes": ["sql", "offline_access"],
        },
    }
    return prepare_user_oauth_config_for_storage(raw, cipher=cipher) if cipher else raw


def _form_create(
    *,
    name: str,
    credential_mode: str,
    config: dict,
    description: str | None = None,
) -> dict[str, str]:
    data = {
        "name": name,
        "type": "databricks",
        "credential_mode": credential_mode,
        "config": json.dumps(config),
    }
    if description is not None:
        data["description"] = description
    return data


@pytest_asyncio.fixture
async def dbx_modes_http_env(async_db_session: AsyncSession, monkeypatch):
    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    suffix = uuid4().hex[:8]
    async with session_factory() as seed_session:
        tenant = Tenant(name=f"dbx_modes_{suffix}", slug=f"dbx-modes-{suffix}", config=None)
        seed_session.add(tenant)
        await seed_session.flush()
        user = User(
            username=f"dbx_admin_{suffix}",
            email=f"dbx_{suffix}@test.local",
            hashed_password="synthetic",
            role="admin",
            tenant_id=tenant.id,
        )
        seed_session.add(user)
        await seed_session.flush()
        seed_session.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, status="active"))
        await seed_data_source_owner_policies(
            seed_session, tenant.id, base_id=6200 + int(suffix[:4], 16) % 500
        )
        await seed_session.commit()

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "apps.shared.infra.analytics_db.manager_factory.get_db_manager_for_datasource",
        lambda _domain: _FakeDbManager(),
    )

    token = _jwt_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    yield {
        "client": client,
        "headers": headers,
        "suffix": suffix,
    }
    await client.aclose()
    app.dependency_overrides.clear()
    await test_engine.dispose()


def _assert_not_password_validation_error(response) -> None:
    text = response.text
    assert "Databricks connection requires password" not in text, text


@pytest.mark.asyncio
async def test_databricks_shared_mode_create_get_update_http(dbx_modes_http_env):
    client: httpx.AsyncClient = dbx_modes_http_env["client"]
    headers = dbx_modes_http_env["headers"]
    suffix = dbx_modes_http_env["suffix"]

    create = await client.post(
        "/data-sources",
        data=_form_create(
            name=f"dbx-shared-{suffix}",
            credential_mode="shared",
            config=_shared_databricks_config(),
        ),
        headers=headers,
    )
    assert create.status_code == 201, create.text
    _assert_not_password_validation_error(create)
    body = create.json()
    ds_id = body["id"]
    assert body["credential_mode"] == "shared"
    assert "config.password" in body.get("masked_fields", [])

    get = await client.get(f"/data-sources/{ds_id}", headers=headers)
    assert get.status_code == 200, get.text

    updated_config = {**_shared_databricks_config(), "catalog": "main"}
    update = await client.put(
        f"/data-sources/{ds_id}",
        data={"config": json.dumps(updated_config), "description": "shared updated"},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    _assert_not_password_validation_error(update)
    assert update.json().get("description") == "shared updated"


@pytest.mark.asyncio
async def test_databricks_byot_pat_create_update_and_member_binding_http(dbx_modes_http_env):
    client = dbx_modes_http_env["client"]
    headers = dbx_modes_http_env["headers"]
    suffix = dbx_modes_http_env["suffix"]

    create = await client.post(
        "/data-sources",
        data=_form_create(
            name=f"dbx-byot-pat-{suffix}",
            credential_mode="user",
            config=_byot_pat_template_config(),
        ),
        headers=headers,
    )
    assert create.status_code == 201, create.text
    _assert_not_password_validation_error(create)
    ds_id = create.json()["id"]
    assert create.json()["credential_mode"] == "user"

    update = await client.put(
        f"/data-sources/{ds_id}",
        data={
            "description": "byot pat template",
            "config": json.dumps(_byot_pat_template_config()),
        },
        headers=headers,
    )
    assert update.status_code == 200, update.text
    _assert_not_password_validation_error(update)

    bind = await client.put(
        f"/data-sources/{ds_id}/connections/me",
        headers=headers,
        json={"auth_type": "pat", "secrets": {"password": "dapi-synthetic-member-pat"}},
    )
    assert bind.status_code == 200, bind.text
    assert bind.json()["status"] == "connected"
    assert "secrets.password" in bind.json().get("masked_fields", [])

    test_conn = await client.post(
        f"/data-sources/{ds_id}/connections/me/test",
        headers=headers,
    )
    assert test_conn.status_code == 200, test_conn.text
    assert test_conn.json()["success"] is True


@pytest.mark.asyncio
async def test_databricks_byot_oauth_create_update_get_and_oauth_start_http(dbx_modes_http_env, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.get_settings",
        lambda: SimpleNamespace(
            TENANT_APP_API_ORIGIN="https://api.example.test",
            PORTAL_ORIGIN="https://portal.example.test",
        ),
    )

    client = dbx_modes_http_env["client"]
    headers = dbx_modes_http_env["headers"]
    suffix = dbx_modes_http_env["suffix"]
    cipher = FieldCipher()

    create = await client.post(
        "/data-sources",
        data=_form_create(
            name=f"dbx-byot-oauth-{suffix}",
            credential_mode="user",
            config=_byot_oauth_template_config(cipher=cipher),
        ),
        headers=headers,
    )
    assert create.status_code == 201, create.text
    _assert_not_password_validation_error(create)
    ds_id = create.json()["id"]

    patch_config = _byot_oauth_template_config()
    block = dict(patch_config[USER_OAUTH_CONFIG_KEY])
    block["client_id"] = "synthetic-client-v2"
    block.pop("client_secret", None)
    patch_config[USER_OAUTH_CONFIG_KEY] = block
    update = await client.put(
        f"/data-sources/{ds_id}",
        data={"config": json.dumps(patch_config), "description": "oauth admin template"},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    _assert_not_password_validation_error(update)
    assert "config.user_oauth.client_secret" in update.json().get("masked_fields", [])

    get = await client.get(f"/data-sources/{ds_id}", headers=headers)
    assert get.status_code == 200, get.text
    assert get.json()["config"].get("user_credential_auth_type") == USER_CREDENTIAL_AUTH_OAUTH2

    oauth_start = await client.post(f"/data-sources/{ds_id}/oauth/start", headers=headers)
    assert oauth_start.status_code == 200, oauth_start.text
    assert oauth_start.json()["authorization_url"].startswith("https://")