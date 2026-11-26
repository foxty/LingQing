"""Integration: Databricks data-source user OAuth connect (real DB, stubbed token HTTP)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.shared.db.models import DataSource, Tenant, User
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
    prepare_user_oauth_config_for_storage,
)
from apps.shared.external_systems.credentials.domain import CREDENTIAL_STATUS_ACTIVE
from apps.shared.external_systems.oauth.flow import IntegrationOAuthFlow
from apps.shared.infra.oauth import OAuth2TokenClient, OAuthTokenSet
from apps.shared.utils.field_cipher import FieldCipher
from apps.tenant_app_service.server import app


def _databricks_oauth_config(cipher: FieldCipher) -> dict:
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    return prepare_user_oauth_config_for_storage(
        {
            "host": "adb-example.azuredatabricks.net",
            "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
            USER_OAUTH_CONFIG_KEY: {
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
                "authorize_url": auth,
                "token_url": token,
                "redirect_uri": "https://api.example.test/integrations/oauth/callback",
                "scopes": ["sql", "offline_access"],
            },
        },
        cipher=cipher,
    )


@pytest.mark.asyncio
async def test_data_source_oauth_callback_http_persists_binding(pg_async_db_session, monkeypatch):
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.get_settings",
        lambda: SimpleNamespace(
            TENANT_APP_API_ORIGIN="https://api.example.test",
            PORTAL_ORIGIN="https://portal.example.test",
        ),
    )

    connection = await pg_async_db_session.connection()
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    suffix = uuid4().hex[:8]
    cipher = FieldCipher()
    actor: ActorContext
    data_source_id: int
    async with session_factory() as seed_session:
        tenant = Tenant(name=f"ds_oauth_http_{suffix}", slug=f"ds-oauth-http-{suffix}", config=None)
        seed_session.add(tenant)
        await seed_session.flush()
        user = User(
            username=f"ds_oauth_{suffix}",
            email=None,
            hashed_password="synthetic",
            role="admin",
            tenant_id=tenant.id,
        )
        seed_session.add(user)
        await seed_session.flush()
        actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)

        data_source = DataSource(
            tenant_id=tenant.id,
            owner_id=user.id,
            name=f"dbx-oauth-{suffix}",
            type="databricks",
            managed=False,
            credential_mode="user",
            config=_databricks_oauth_config(cipher),
            description="OAuth U2M",
        )
        seed_session.add(data_source)
        await seed_session.flush()
        data_source_id = data_source.id
        await seed_session.commit()

    async with session_factory() as flow_session:
        flow = IntegrationOAuthFlow(flow_session)
        authorize_url = await flow.start(
            actor=actor,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source_id,
        )
        state = parse_qs(urlsplit(authorize_url).query)["state"][0]

    exchange = AsyncMock(
        return_value=OAuthTokenSet(
            access_token="dbx-access-http",
            refresh_token="dbx-refresh-http",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    monkeypatch.setattr(OAuth2TokenClient, "exchange_code", exchange)

    async def override_get_db():
        async with session_factory() as db_session:
            try:
                yield db_session
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise
            finally:
                await db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/integrations/oauth/callback",
                params={"code": "auth-code", "state": state},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in (302, 307)
    assert response.headers["location"] == (
        f"https://portal.example.test/data-sources?ds={data_source_id}&oauth=connected"
    )
    exchange.assert_awaited_once()

    async with session_factory() as verify_session:
        repo = UserIntegrationCredentialRepository(verify_session)
        binding = await repo.get_binding(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source_id,
        )
        assert binding is not None
        assert binding.auth_type == "oauth2"
        secrets = cipher.decrypt_dict(binding.secrets_enc, sensitive_fields={"access_token", "refresh_token"})
        assert secrets["access_token"] == "dbx-access-http"
        assert binding.status == CREDENTIAL_STATUS_ACTIVE