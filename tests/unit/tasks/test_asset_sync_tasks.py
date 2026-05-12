from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from apps.shared.tasks.system.jobs.asset_sync import _sync_tenant_assets


class _AsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_sync_tenant_assets_resolves_data_source_ids_per_tenant():
    tenant_id = 1
    session = AsyncMock()

    execute_result = MagicMock()
    execute_result.all.return_value = [(11,), (12,)]
    session.execute = AsyncMock(return_value=execute_result)

    asset_service = AsyncMock()
    asset_service.sync_all_assets = AsyncMock(
        return_value={
            "status": "success",
            "updated_count": 1,
            "skipped_count": 0,
            "error_count": 0,
        }
    )

    ds_service = AsyncMock()
    ds_service.get_db_manager = AsyncMock(side_effect=["manager-11", "manager-12"])

    with (
        patch("apps.shared.tasks.system.jobs.asset_sync.app_db_session", return_value=_AsyncSessionContext(session)),
        patch("apps.shared.tasks.system.jobs.asset_sync.AssetMetadataRepository"),
        patch("apps.shared.tasks.system.jobs.asset_sync.DataSourceRepository"),
        patch("apps.shared.tasks.system.jobs.asset_sync.AssetMetadataService", return_value=asset_service),
        patch("apps.shared.tasks.system.jobs.asset_sync.DataSourceService", return_value=ds_service),
    ):
        result = await _sync_tenant_assets(tenant_id=tenant_id)

    assert result["status"] == "success"
    assert result["tenant_id"] == tenant_id
    assert result["updated_count"] == 1

    ds_service.get_db_manager.assert_has_awaits([call(11), call(12)])
    asset_service.sync_all_assets.assert_awaited_once_with(
        db_managers={11: "manager-11", 12: "manager-12"},
        data_source_ids=[11, 12],
    )
