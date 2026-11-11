"""DataSourceService.test_saved_data_source_connection"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.external_systems.data_source.catalog_sync import API_SECRET_PLACEHOLDER
from apps.shared.external_systems.data_source.service import DataSourceService


def _fake_entity(*, credential_mode="user", managed=False, config=None):
    entity = MagicMock()
    entity.managed = managed
    entity.credential_mode = credential_mode
    entity.type = "postgres"
    entity.config = config or {}
    return entity


@pytest.mark.asyncio
async def test_saved_connection_user_mode_merges_stored_sync_password_from_overlay():
    repo = AsyncMock()
    repo.get_by_id_and_tenant = AsyncMock(
        return_value=_fake_entity(
            config={
                "host": "db.internal",
                "port": 5432,
                "database": "app",
                "metadata_sync": {"username": "sync_u", "password": "secret-p"},
            }
        )
    )
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=repo,
        asset_repo=SimpleNamespace(db=MagicMock()),
    )

    manager = AsyncMock()
    manager.__aenter__ = AsyncMock(return_value=manager)
    manager.__aexit__ = AsyncMock(return_value=False)
    manager.test_connection = AsyncMock(return_value=(True, "ok"))

    overlay = {
        "host": "localhost",
        "port": 5432,
        "database": "lq_tenant_app",
        "metadata_sync": {"username": "sync_u", "password": API_SECRET_PLACEHOLDER},
    }

    with patch(
        "apps.shared.external_systems.data_source.service.get_db_manager_for_datasource",
        return_value=manager,
    ):
        result = await service.test_saved_data_source_connection(9, config_overlay=overlay)

    assert result.success is True
    manager.test_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_saved_connection_shared_mode_merges_stored_root_password():
    repo = AsyncMock()
    repo.get_by_id_and_tenant = AsyncMock(
        return_value=_fake_entity(
            credential_mode="shared",
            config={
                "host": "db.internal",
                "port": 5432,
                "database": "app",
                "username": "app",
                "password": "secret-shared",
            },
        )
    )
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=repo,
        asset_repo=SimpleNamespace(db=MagicMock()),
    )

    manager = AsyncMock()
    manager.__aenter__ = AsyncMock(return_value=manager)
    manager.__aexit__ = AsyncMock(return_value=False)
    manager.test_connection = AsyncMock(return_value=(True, "ok"))

    overlay = {
        "host": "localhost",
        "port": 5432,
        "database": "lq_tenant_app",
        "username": "app",
        "password": API_SECRET_PLACEHOLDER,
    }

    with patch(
        "apps.shared.external_systems.data_source.service.get_db_manager_for_datasource",
        return_value=manager,
    ):
        result = await service.test_saved_data_source_connection(9, config_overlay=overlay)

    assert result.success is True
    manager.test_connection.assert_awaited_once()
