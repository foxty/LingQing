"""Data-source service paths that must decrypt persisted config before merge or connect."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.external_systems.data_source.config_secrets_policy import (
    prepare_data_source_config_for_storage,
)
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.utils.field_cipher import FieldCipher


def _fake_entity(*, credential_mode="user", managed=False, config=None):
    entity = MagicMock()
    entity.managed = managed
    entity.credential_mode = credential_mode
    entity.type = "postgres"
    entity.tenant_id = 1
    entity.config = config or {}
    return entity


@pytest.mark.asyncio
async def test_saved_connection_decrypts_encrypted_metadata_sync_password():
    cipher = FieldCipher()
    stored = prepare_data_source_config_for_storage(
        {
            "host": "db.internal",
            "port": 5432,
            "database": "app",
            "metadata_sync": {"username": "sync_u", "password": "secret-p"},
        },
        cipher=cipher,
    )
    repo = AsyncMock()
    repo.get_by_id_and_tenant = AsyncMock(return_value=_fake_entity(config=stored))
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=repo,
        asset_repo=SimpleNamespace(db=MagicMock()),
    )

    manager = AsyncMock()
    manager.__aenter__ = AsyncMock(return_value=manager)
    manager.__aexit__ = AsyncMock(return_value=False)
    manager.test_connection = AsyncMock(return_value=(True, "ok"))

    with patch(
        "apps.shared.external_systems.data_source.service.get_db_manager_for_datasource",
        return_value=manager,
    ) as get_manager:
        result = await service.test_saved_data_source_connection(9, config_overlay=None)

    assert result.success is True
    domain = get_manager.call_args[0][0]
    assert domain.connection.password == "secret-p"


@pytest.mark.asyncio
async def test_metadata_sync_manager_uses_decrypted_sync_password():
    cipher = FieldCipher()
    stored = prepare_data_source_config_for_storage(
        {
            "host": "db.internal",
            "port": 5432,
            "database": "app",
            "metadata_sync": {"username": "sync_u", "password": "sync-secret"},
        },
        cipher=cipher,
    )
    entity = _fake_entity(config=stored)
    entity.id = 42
    repo = AsyncMock()
    repo.get_by_id_and_tenant = AsyncMock(return_value=entity)
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=repo,
        asset_repo=SimpleNamespace(db=MagicMock()),
    )

    manager = MagicMock()
    with patch.object(service, "get_db_manager", new=AsyncMock()) as shared_mgr:
        with patch(
            "apps.shared.external_systems.data_source.service.get_db_manager_for_datasource",
            return_value=manager,
        ) as get_manager:
            await service.get_db_manager_for_metadata_sync(42)

    domain = get_manager.call_args[0][0]
    assert domain.connection.password == "sync-secret"
    shared_mgr.assert_not_awaited()