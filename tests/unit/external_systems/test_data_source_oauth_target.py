"""Unit tests for DataSourceOAuthTarget guardrails and spec loading."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
)
from apps.shared.external_systems.oauth.flow import DataSourceOAuthTarget
from apps.shared.utils.field_cipher import FieldCipher

_CIPHER_KEY = "synthetic-ds-target-key"


def _entity(*, credential_mode="user", managed=False, auth_type=USER_CREDENTIAL_AUTH_OAUTH2, ds_type="databricks"):
    cipher = FieldCipher(_CIPHER_KEY)
    authorize_url, token_url = databricks_oidc_urls("adb-example.azuredatabricks.net")
    config = {"host": "adb-example.azuredatabricks.net"}
    if auth_type == USER_CREDENTIAL_AUTH_OAUTH2:
        config["user_credential_auth_type"] = USER_CREDENTIAL_AUTH_OAUTH2
        config[USER_OAUTH_CONFIG_KEY] = cipher.encrypt_dict(
            {
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
                "authorize_url": authorize_url,
                "token_url": token_url,
                "redirect_uri": "https://api.example.test/integrations/oauth/callback",
                "scopes": ["sql", "offline_access"],
            },
            sensitive_fields={"client_secret"},
        )
    return SimpleNamespace(
        id=11,
        tenant_id=3,
        type=ds_type,
        managed=managed,
        credential_mode=credential_mode,
        config=config,
    )


@pytest.fixture
def target():
    return DataSourceOAuthTarget(SimpleNamespace(), cipher=FieldCipher(_CIPHER_KEY))


@pytest.mark.asyncio
async def test_load_oauth_spec_returns_connector_spec(target, monkeypatch):
    entity = _entity()
    monkeypatch.setattr(target._repo, "get_by_id_and_tenant", AsyncMock(return_value=entity))
    actor = ActorContext(tenant_id=3, user_id=7, user_role="member")
    spec = await target.load_oauth_spec(actor=actor, resource_id=11)
    assert spec.client_id == "synthetic-client"
    assert spec.redirect_uri == "https://api.example.test/integrations/oauth/callback"
    assert "sql" in spec.scopes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity,match",
    [
        (None, "not found"),
        (_entity(credential_mode="shared"), "per-user"),
        (_entity(managed=True), "per-user"),
        (_entity(ds_type="postgres"), "Databricks"),
        (_entity(auth_type="pat"), "user OAuth2"),
    ],
)
async def test_load_oauth_spec_rejects_invalid_data_source(target, monkeypatch, entity, match):
    monkeypatch.setattr(target._repo, "get_by_id_and_tenant", AsyncMock(return_value=entity))
    actor = ActorContext(tenant_id=3, user_id=7, user_role="member")
    with pytest.raises((ValidationError, ResourceNotFoundError), match=match):
        await target.load_oauth_spec(actor=actor, resource_id=11)