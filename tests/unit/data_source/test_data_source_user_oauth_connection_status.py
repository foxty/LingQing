"""DataSourceService: OAuth2 user connection status on list (no token refresh on status)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.schemas import DataSourceCreate
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
)
from apps.shared.external_systems.domain.types import USER_CONNECTION_CONNECTED
from apps.shared.infra.oauth import OAuth2TokenClient
from apps.shared.utils.field_cipher import FieldCipher
from tests.helpers.data_source_fixtures import seed_data_source_owner_policies
from tests.helpers.document_fixtures import create_tenant_user


def _oauth_user_config() -> dict:
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    return {
        "host": "adb-example.azuredatabricks.net",
        "extra_params": {"http_path": "/sql/1.0/warehouses/synthetic"},
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


@pytest.mark.asyncio
async def test_list_user_connection_status_connected_when_access_stale_but_refresh_token_present(
    async_db_session,
    monkeypatch,
):
    async def forbid_token_refresh(self, **kwargs):
        raise AssertionError("OAuth token refresh must not run during list/status enrichment")

    monkeypatch.setattr(OAuth2TokenClient, "refresh", forbid_token_refresh)

    tenant, owner = await create_tenant_user(
        async_db_session,
        tenant_name="ds-oauth-list-status",
        username="ds-oauth-list-user",
    )
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9200)
    service = DataSourceService(
        tenant_id=tenant.id,
        data_source_repo=DataSourceRepository(async_db_session),
        asset_repo=AssetMetadataRepository(async_db_session),
    )
    created = await service.create_data_source(
        DataSourceCreate(
            name="dbx-oauth-list-status",
            type="databricks",
            managed=False,
            credential_mode="user",
            config=_oauth_user_config(),
        ),
        owner_id=owner.id,
    )

    cipher = FieldCipher()
    cred_repo = UserIntegrationCredentialRepository(async_db_session)
    await cred_repo.upsert_binding(
        tenant_id=tenant.id,
        user_id=owner.id,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=created.id,
        auth_type="oauth2",
        secrets_enc=cipher.encrypt_dict(
            {"access_token": "stale-access", "refresh_token": "still-have-refresh"},
            sensitive_fields={"access_token", "refresh_token"},
        ),
        account_label="dbx-user",
        expires_at=datetime.now(UTC) - timedelta(hours=4),
    )

    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="admin")
    domains = await service.list_data_sources_for_actor(actor=actor)
    match = next((d for d in domains if d.id == created.id), None)
    assert match is not None
    assert match.user_connection_status == USER_CONNECTION_CONNECTED