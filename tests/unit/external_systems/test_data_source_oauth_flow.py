"""Integration OAuth flow tests for DataSourceOAuthTarget."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.oauth.flow import DataSourceOAuthTarget, IntegrationOAuthFlow
from apps.shared.external_systems.oauth.state import OAuthStateCodec
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
)
from apps.shared.infra.oauth import OAuthTokenSet
from apps.shared.utils.field_cipher import FieldCipher


@pytest.mark.asyncio
async def test_data_source_oauth_target_completes_callback(monkeypatch):
    cipher = FieldCipher("synthetic-ds-oauth-flow-key")
    authorize_url, token_url = databricks_oidc_urls("adb-example.azuredatabricks.net")
    entity = SimpleNamespace(
        id=91,
        tenant_id=5,
        type="databricks",
        managed=False,
        credential_mode="user",
        config={
            "host": "adb-example.azuredatabricks.net",
            "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
            USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
                {
                    "client_id": "synthetic-client",
                    "client_secret": "synthetic-secret",
                    "authorize_url": authorize_url,
                    "token_url": token_url,
                    "redirect_uri": "https://api.example.test/integrations/oauth/callback",
                    "scopes": ["sql", "offline_access"],
                },
                sensitive_fields={"client_secret"},
            ),
        },
    )

    target = DataSourceOAuthTarget(SimpleNamespace(), cipher=cipher)
    monkeypatch.setattr(target._repo, "get_by_id_and_tenant", AsyncMock(return_value=entity))

    codec = OAuthStateCodec(cipher)
    flow = IntegrationOAuthFlow(
        SimpleNamespace(),
        token_client=SimpleNamespace(
            exchange_code=AsyncMock(
                return_value=OAuthTokenSet(
                    access_token="dbx-access",
                    refresh_token="dbx-refresh",
                    token_type="Bearer",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        ),
        state_codec=codec,
        targets={RESOURCE_TYPE_DATA_SOURCE: target},
    )

    upsert = AsyncMock()
    monkeypatch.setattr(
        "apps.shared.external_systems.oauth.flow.UserIntegrationCredentialService",
        lambda _db: SimpleNamespace(upsert_data_source_connection=upsert),
    )

    actor = ActorContext(tenant_id=5, user_id=12, user_role="member")
    authorize_url = await flow.start(
        actor=actor,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=91,
    )
    assert "synthetic-client" in authorize_url

    from urllib.parse import parse_qs, urlsplit

    state = parse_qs(urlsplit(authorize_url).query)["state"][0]
    outcome = await flow.complete_from_callback(code="code", state=state)

    assert outcome.resource_id == 91
    assert "data-sources" in outcome.portal_url
    upsert.assert_awaited_once()
    assert upsert.await_args.kwargs["body"].auth_type == "oauth2"