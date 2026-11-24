from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.domain import OAuth2AuthConfig
from apps.shared.external_systems.oauth.flow import OAUTH_CALLBACK_PATH, ApiConnectorOAuthFlow
from apps.shared.external_systems.oauth.state import OAuthStateCodec
from apps.shared.infra.oauth import OAuthTokenSet
from apps.shared.utils.field_cipher import FieldCipher


@pytest.mark.asyncio
async def test_complete_from_callback_uses_state_actor(monkeypatch):
    cipher = FieldCipher("synthetic-oauth-callback-key")
    codec = OAuthStateCodec(cipher)
    state, verifier = codec.issue(
        tenant_id=9,
        user_id=8,
        connector_id=4,
        redirect_uri=f"https://api.example.test{OAUTH_CALLBACK_PATH}",
    )

    flow = ApiConnectorOAuthFlow(SimpleNamespace(), state_codec=codec)
    config = OAuth2AuthConfig(
        authorize_url="https://auth.example.test/authorize",
        token_url="https://auth.example.test/token",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )
    monkeypatch.setattr(flow, "_oauth_config", AsyncMock(return_value=config))

    exchange = AsyncMock(
        return_value=OAuthTokenSet(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    flow._token_client.exchange_code = exchange
    upsert = AsyncMock(return_value=SimpleNamespace(status="connected"))
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.UserIntegrationCredentialService",
        lambda _db: SimpleNamespace(upsert_api_connector_connection=upsert),
    )

    connector_id = await flow.complete_from_callback(code="auth-code", state=state)

    assert connector_id == 4
    exchange.assert_awaited_once()
    assert exchange.await_args.kwargs["code_verifier"] == verifier
    actor: ActorContext = upsert.await_args.kwargs["actor"]
    assert actor.tenant_id == 9
    assert actor.user_id == 8
    assert upsert.await_args.kwargs["connector_id"] == 4


def test_default_redirect_uri_targets_api_callback(monkeypatch):
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.get_settings",
        lambda: SimpleNamespace(TENANT_APP_API_ORIGIN="https://api.example.test/"),
    )
    assert ApiConnectorOAuthFlow._default_redirect_uri() == f"https://api.example.test{OAUTH_CALLBACK_PATH}"
