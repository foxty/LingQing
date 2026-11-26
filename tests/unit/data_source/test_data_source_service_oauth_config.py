"""DataSourceService persistence rules for Databricks user OAuth config."""

from __future__ import annotations

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.schemas import DataSourceCreate, DataSourceUpdate
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
)
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
async def test_create_data_source_encrypts_user_oauth_secret(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-oauth-create", username="ds-admin")
    service = DataSourceService(
        tenant_id=tenant.id,
        data_source_repo=DataSourceRepository(async_db_session),
        asset_repo=AssetMetadataRepository(async_db_session),
    )
    created = await service.create_data_source(
        DataSourceCreate(
            name="dbx-oauth-u2m",
            type="databricks",
            managed=False,
            credential_mode="user",
            config=_oauth_user_config(),
        ),
        owner_id=owner.id,
    )
    entity = await service.data_source_repo.get_by_id_and_tenant(created.id, tenant.id)
    assert entity is not None
    secret = entity.config[USER_OAUTH_CONFIG_KEY]["client_secret"]
    assert secret.startswith("enc:")


@pytest.mark.asyncio
async def test_create_data_source_rejects_oauth_without_redirect_uri(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-oauth-bad", username="ds-admin-bad")
    service = DataSourceService(
        tenant_id=tenant.id,
        data_source_repo=DataSourceRepository(async_db_session),
        asset_repo=AssetMetadataRepository(async_db_session),
    )
    bad = _oauth_user_config()
    bad[USER_OAUTH_CONFIG_KEY].pop("redirect_uri")
    with pytest.raises(ValidationError, match="redirect_uri"):
        await service.create_data_source(
            DataSourceCreate(
                name="dbx-oauth-bad",
                type="databricks",
                managed=False,
                credential_mode="user",
                config=bad,
            ),
            owner_id=owner.id,
        )


@pytest.mark.asyncio
async def test_update_data_source_merge_preserves_user_oauth_client_secret(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-oauth-patch", username="ds-patcher")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9100)
    service = DataSourceService(
        tenant_id=tenant.id,
        data_source_repo=DataSourceRepository(async_db_session),
        asset_repo=AssetMetadataRepository(async_db_session),
    )
    cipher = FieldCipher()
    created = await service.create_data_source(
        DataSourceCreate(
            name="dbx-oauth-patch",
            type="databricks",
            managed=False,
            credential_mode="user",
            config=_oauth_user_config(),
        ),
        owner_id=owner.id,
    )
    from apps.shared.domain.actor import ActorContext

    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="admin")
    await service.update_data_source_for_actor(
        data_source_id=created.id,
        update_data=DataSourceUpdate(
            config={
                "host": "adb-example.azuredatabricks.net",
                USER_OAUTH_CONFIG_KEY: {"client_id": "synthetic-client-v2"},
            }
        ),
        actor=actor,
    )
    entity = await service.data_source_repo.get_by_id_and_tenant(created.id, tenant.id)
    plain = cipher.decrypt(entity.config[USER_OAUTH_CONFIG_KEY]["client_secret"])
    assert plain == "synthetic-secret"
    assert entity.config[USER_OAUTH_CONFIG_KEY]["client_id"] == "synthetic-client-v2"