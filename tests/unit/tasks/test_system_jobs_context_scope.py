from unittest.mock import AsyncMock

import pytest

from apps.shared.tasks.system.jobs import asset_sync, vector_sync


@pytest.mark.asyncio
async def test_asset_sync_uses_context_scoped_tenant(monkeypatch):
    seen_tenant_ids = []

    monkeypatch.setattr(
        asset_sync,
        "_sync_tenant_assets",
        AsyncMock(
        side_effect=lambda tenant_id: seen_tenant_ids.append(tenant_id)
        or {"status": "success", "updated_count": 0, "skipped_count": 0, "error_count": 0}
        ),
    )

    result = await asset_sync.sync_asset_metadata_for_all(task_context={"tenant_id": 7})

    assert seen_tenant_ids == [7]
    assert result.outcome == "success"
    assert result.data["total_tenants"] == 1


@pytest.mark.asyncio
async def test_vector_cleanup_uses_context_scoped_tenant(monkeypatch):
    monkeypatch.setattr(
        vector_sync,
        "_cleanup_by_resource_type",
        AsyncMock(return_value={"orphaned_count": 0, "cleaned_count": 0}),
    )

    result = await vector_sync.cleanup_orphaned_vectors(task_context={"tenant_id": 9})

    assert vector_sync._cleanup_by_resource_type.await_count == len(vector_sync._RESOURCE_TYPE_MAP)
    assert result.outcome == "success"
    assert result.data["total_orphaned"] == 0
