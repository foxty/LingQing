from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.api_connector.domain import OAuth2AuthConfig
from apps.shared.external_systems.oauth.flow import (
    INTEGRATION_OAUTH_CALLBACK_PATH,
    ApiConnectorOAuthTarget,
    IntegrationOAuthFlow,
    OAuthAuthorizationSpec,
    append_oauth_error_hints,
)
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
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=4,
        redirect_uri=f"https://api.example.test{INTEGRATION_OAUTH_CALLBACK_PATH}",
    )

    config = OAuth2AuthConfig(
        authorize_url="https://auth.example.test/authorize",
        token_url="https://auth.example.test/token",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )
    target = ApiConnectorOAuthTarget(SimpleNamespace(), cipher=cipher)
    monkeypatch.setattr(target, "load_oauth_config", AsyncMock(return_value=config))

    exchange = AsyncMock(
        return_value=OAuthTokenSet(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    flow = IntegrationOAuthFlow(
        SimpleNamespace(),
        token_client=SimpleNamespace(exchange_code=exchange),
        state_codec=codec,
        targets={RESOURCE_TYPE_API_CONNECTOR: target},
    )
    upsert = AsyncMock(return_value=SimpleNamespace(status="connected"))
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.UserIntegrationCredentialService",
        lambda _db: SimpleNamespace(upsert_api_connector_connection=upsert),
    )

    outcome = await flow.complete_from_callback(code="auth-code", state=state)

    assert outcome.resource_type == RESOURCE_TYPE_API_CONNECTOR
    assert outcome.resource_id == 4
    exchange.assert_awaited_once()
    assert exchange.await_args.kwargs["code_verifier"] == verifier
    actor: ActorContext = upsert.await_args.kwargs["actor"]
    assert actor.tenant_id == 9
    assert actor.user_id == 8
    assert upsert.await_args.kwargs["connector_id"] == 4


@pytest.mark.asyncio
async def test_integration_oauth_flow_routes_custom_resource_target(monkeypatch):
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.get_settings",
        lambda: SimpleNamespace(
            TENANT_APP_API_ORIGIN="https://api.example.test/",
            PORTAL_ORIGIN="https://portal.example.test/",
        ),
    )
    cipher = FieldCipher("synthetic-ds-oauth-key")
    codec = OAuthStateCodec(cipher)
    saved_calls: list[dict] = []

    class _FakeDataSourceTarget:
        resource_type = RESOURCE_TYPE_DATA_SOURCE

        async def load_oauth_spec(self, *, actor: ActorContext, resource_id: int) -> OAuthAuthorizationSpec:
            return OAuthAuthorizationSpec(
                authorize_url="https://dbx.example.test/oidc/v1/authorize",
                token_url="https://dbx.example.test/oidc/v1/token",
                client_id="synthetic-dbx-client",
                client_secret="synthetic-dbx-secret",
                scopes=("sql", "offline_access"),
            )

        async def save_tokens(self, *, actor: ActorContext, resource_id: int, tokens: OAuthTokenSet):
            saved_calls.append({"actor": actor, "resource_id": resource_id, "tokens": tokens})
            return SimpleNamespace(status="connected")

        @staticmethod
        def portal_success_url(resource_id: int) -> str:
            return f"https://portal.example.test/data-sources?ds={resource_id}&oauth=connected"

        @staticmethod
        def portal_error_url(*, resource_id: int | None = None) -> str:
            return f"https://portal.example.test/data-sources?ds={resource_id}&oauth=error"

    token_client = SimpleNamespace(
        exchange_code=AsyncMock(
            return_value=OAuthTokenSet(
                access_token="dbx-access",
                refresh_token="dbx-refresh",
                token_type="Bearer",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    )
    flow = IntegrationOAuthFlow(
        SimpleNamespace(),
        token_client=token_client,
        state_codec=codec,
        targets={RESOURCE_TYPE_DATA_SOURCE: _FakeDataSourceTarget()},
    )

    actor = ActorContext(tenant_id=12, user_id=34, user_role="member")
    authorize_url = await flow.start(
        actor=actor,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=77,
    )
    assert "scope=sql+offline_access" in authorize_url

    from urllib.parse import parse_qs, urlsplit

    state = parse_qs(urlsplit(authorize_url).query)["state"][0]
    assert flow.portal_error_url_for_state(state) == ("https://portal.example.test/data-sources?ds=77&oauth=error")

    outcome = await flow.complete_from_callback(code="dbx-code", state=state)
    assert outcome.resource_type == RESOURCE_TYPE_DATA_SOURCE
    assert outcome.resource_id == 77
    assert outcome.portal_url == "https://portal.example.test/data-sources?ds=77&oauth=connected"
    assert len(saved_calls) == 1
    assert saved_calls[0]["actor"].user_id == 34


def test_append_oauth_error_hints_adds_query_params():
    url = "https://portal.example.test/data-sources?ds=7&oauth=error"
    enriched = append_oauth_error_hints(
        url,
        oauth_code="access_denied",
        oauth_detail="User declined consent",
        oauth_reason="token_exchange_failed",
    )
    assert "oauth=error" in enriched
    assert "ds=7" in enriched
    assert "oauth_code=access_denied" in enriched
    assert "oauth_detail=User+declined+consent" in enriched
    assert "oauth_reason=token_exchange_failed" in enriched


def test_api_connector_default_redirect_uri_uses_integration_callback(monkeypatch):
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.get_settings",
        lambda: SimpleNamespace(TENANT_APP_API_ORIGIN="https://api.example.test/"),
    )
    config = OAuth2AuthConfig(
        authorize_url="https://auth.example.test/authorize",
        token_url="https://auth.example.test/token",
        client_id="synthetic-client",
    )

    spec = ApiConnectorOAuthTarget.spec_from_connector_config(config)

    assert spec.redirect_uri == (f"https://api.example.test{INTEGRATION_OAUTH_CALLBACK_PATH}")
