"""Resolver BYOT template overlay and persisted refresh encryption."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.domain.types import IntegrationPurpose
from apps.shared.infra.oauth import OAuth2TokenClient, OAuthTokenSet
from apps.shared.utils.field_cipher import FieldCipher


def test_merge_user_secrets_strips_shared_api_key_before_overlay():
    template = {
        "client_id": "shared-app",
        "api_key": "shared-key",
        "endpoint": "https://api.example.test",
    }
    user = {"api_key": "user-key"}
    merged = IntegrationCredentialResolver._merge_user_secrets_into_connector_template(
        template=template,
        user_secrets=user,
        auth_type="basic",
    )
    assert merged == {"client_id": "shared-app", "endpoint": "https://api.example.test", "api_key": "user-key"}


def test_merge_user_secrets_oauth2_keeps_app_client_strips_template_tokens():
    template = {
        "client_id": "app",
        "client_secret": "shared-secret",
        "access_token": "stale-template-token",
    }
    user = {"access_token": "user-token", "refresh_token": "user-refresh"}
    merged = IntegrationCredentialResolver._merge_user_secrets_into_connector_template(
        template=template,
        user_secrets=user,
        auth_type="oauth2",
    )
    assert merged["client_secret"] == "shared-secret"
    assert merged["access_token"] == "user-token"
    assert merged["refresh_token"] == "user-refresh"
    assert "stale-template-token" not in merged.values()


@pytest.mark.asyncio
async def test_oauth_refresh_persists_binding_with_prepare_user_binding(monkeypatch):
    cipher = FieldCipher("synthetic-resolver-refresh-persist-key")
    db = SimpleNamespace(flush=AsyncMock())
    resolver = IntegrationCredentialResolver(db, cipher=cipher)
    connector = SimpleNamespace(
        id=31,
        tenant_id=17,
        credential_mode="user",
        auth_type="oauth2",
        auth_config=cipher.encrypt_dict(
            {
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
            {"access_token": "expired-token", "refresh_token": "refresh-token"},
            sensitive_fields={"access_token", "refresh_token"},
        ),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        updated_at=None,
    )
    resolver.repo = SimpleNamespace(get_binding=AsyncMock(return_value=binding))

    async def fake_refresh(self, *, config, refresh_token):
        return OAuthTokenSet(
            access_token="new-token",
            refresh_token=None,
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    monkeypatch.setattr(OAuth2TokenClient, "refresh", fake_refresh)

    await resolver.resolve_api_connector_auth_config(
        connector=connector,
        actor=ActorContext(tenant_id=17, user_id=23, user_role="member"),
        purpose=IntegrationPurpose.EXECUTE,
    )

    assert binding.secrets_enc["access_token"].startswith("enc:")
    assert binding.secrets_enc["refresh_token"].startswith("enc:")