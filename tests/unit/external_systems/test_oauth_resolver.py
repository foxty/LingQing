from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.db.models import DataSource
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
)
from apps.shared.external_systems.domain.types import IntegrationPurpose
from apps.shared.infra.oauth import OAuth2TokenClient, OAuthTokenSet
from apps.shared.utils.field_cipher import FieldCipher


@pytest.mark.asyncio
async def test_resolver_refreshes_expired_oauth_user_token(monkeypatch):
    cipher = FieldCipher("synthetic-oauth-resolver-key")
    db = SimpleNamespace(flush=AsyncMock())
    resolver = IntegrationCredentialResolver(db, cipher=cipher)
    connector = SimpleNamespace(
        id=31,
        tenant_id=17,
        credential_mode="user",
        auth_type="oauth2",
        auth_config=cipher.encrypt_dict(
            {
                "authorize_url": "https://auth.example.test/authorize",
                "token_url": "https://auth.example.test/token",
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
            },
            sensitive_fields={"client_secret"},
        ),
    )
    binding = SimpleNamespace(
        status="active",
        secrets_enc=cipher.encrypt_dict(
            {
                "access_token": "expired-token",
                "refresh_token": "refresh-token",
                "token_url": "https://attacker.example.test/token",
                "client_id": "attacker-client",
            },
            sensitive_fields={"access_token", "refresh_token"},
        ),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        updated_at=None,
    )
    resolver.repo = SimpleNamespace(get_binding=AsyncMock(return_value=binding))

    async def fake_refresh(self, *, config, refresh_token):
        assert config.token_url == "https://auth.example.test/token"
        assert config.client_id == "synthetic-client"
        assert config.client_secret == "synthetic-secret"
        assert refresh_token == "refresh-token"
        return OAuthTokenSet(
            access_token="new-token",
            refresh_token=None,
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    monkeypatch.setattr(OAuth2TokenClient, "refresh", fake_refresh)

    resolved = await resolver.resolve_api_connector_auth_config(
        connector=connector,
        actor=ActorContext(tenant_id=17, user_id=23, user_role="member"),
        purpose=IntegrationPurpose.EXECUTE,
    )

    assert resolved["access_token"] == "new-token"
    assert resolved["refresh_token"] == "refresh-token"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolver_refreshes_expired_oauth_data_source_token(monkeypatch):
    cipher = FieldCipher("synthetic-ds-oauth-resolver-key")
    db = SimpleNamespace(flush=AsyncMock())
    resolver = IntegrationCredentialResolver(db, cipher=cipher)
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    data_source = DataSource(
        id=17,
        tenant_id=9,
        name="dbx-u2m",
        type="databricks",
        managed=False,
        credential_mode="user",
        owner_id=1,
        config={
            "host": "adb-example.azuredatabricks.net",
            "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
            USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
                {
                    "client_id": "synthetic-client",
                    "client_secret": "synthetic-secret",
                    "authorize_url": auth,
                    "token_url": token,
                    "redirect_uri": "https://api.example.test/integrations/oauth/callback",
                    "scopes": ["sql:read:restricted-query", "offline_access"],
                },
                sensitive_fields={"client_secret"},
            ),
        },
    )
    binding = SimpleNamespace(
        status="active",
        auth_type="oauth2",
        secrets_enc=cipher.encrypt_dict(
            {
                "access_token": "expired-dbx",
                "refresh_token": "dbx-refresh",
            },
            sensitive_fields={"access_token", "refresh_token"},
        ),
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
        updated_at=None,
    )
    resolver.repo = SimpleNamespace(get_binding=AsyncMock(return_value=binding))

    async def fake_refresh(self, *, config, refresh_token):
        assert config.token_url == token
        assert config.client_id == "synthetic-client"
        assert config.client_secret == "synthetic-secret"
        assert refresh_token == "dbx-refresh"
        return OAuthTokenSet(
            access_token="fresh-dbx-token",
            refresh_token=None,
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    monkeypatch.setattr(OAuth2TokenClient, "refresh", fake_refresh)

    resolved = await resolver.resolve_data_source_config(
        data_source=data_source,
        actor=ActorContext(tenant_id=9, user_id=4, user_role="member"),
        purpose=IntegrationPurpose.EXECUTE,
    )

    assert resolved["password"] == "fresh-dbx-token"
    assert "password" not in resolved or resolved.get("host") == "adb-example.azuredatabricks.net"
    db.flush.assert_awaited_once()
