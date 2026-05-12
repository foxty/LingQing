from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.core.exceptions import InternalServiceError
from apps.shared.data_source.asset_metadata_service import AssetMetadataService


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


@pytest.mark.asyncio
async def test_sync_all_assets_uses_db_session_without_repo_session():
    db_session = SimpleNamespace(
        commit=AsyncMock(),
    )

    service = AssetMetadataService(tenant_id=1, db_session=db_session)

    service.asset_repo = SimpleNamespace(
        list_sync_candidates_by_tenant=AsyncMock(
            return_value=[SimpleNamespace(id=10, data_source_id=20)]
        ),
        get_by_id=AsyncMock(return_value=None),
        update=AsyncMock(),
    )
    service._sync_asset_metadata_connected = AsyncMock(return_value={"updated": False})

    result = await service.sync_all_assets(db_managers={20: _DbManagerStub()})

    assert result["status"] == "success"
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 1
    service.asset_repo.list_sync_candidates_by_tenant.assert_awaited_once_with(
        tenant_id=1,
        data_source_ids=None,
    )
    db_session.commit.assert_awaited_once()


class _DbManagerStub:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_sync_all_assets_marks_partial_status_when_errors_present():
    db_session = SimpleNamespace(commit=AsyncMock())
    service = AssetMetadataService(tenant_id=1, db_session=db_session)

    service.asset_repo = SimpleNamespace(
        list_sync_candidates_by_tenant=AsyncMock(
            return_value=[
                SimpleNamespace(id=10, data_source_id=20),
                SimpleNamespace(id=11, data_source_id=20),
            ]
        ),
        get_by_id=AsyncMock(return_value=None),
        update=AsyncMock(),
    )
    service._sync_asset_metadata_connected = AsyncMock(
        side_effect=[
            {"updated": True},
            Exception("discover failed"),
        ]
    )
    service._record_asset_sync_error = AsyncMock()

    result = await service.sync_all_assets(db_managers={20: _DbManagerStub()})

    assert result["status"] == "partial"
    assert result["updated_count"] == 1
    assert result["error_count"] == 1
    service._record_asset_sync_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_all_assets_raises_when_db_session_missing():
    service = AssetMetadataService(tenant_id=1, db_session=None)

    with pytest.raises(InternalServiceError, match="Database session is required for asset sync"):
        await service.sync_all_assets(db_managers={})
