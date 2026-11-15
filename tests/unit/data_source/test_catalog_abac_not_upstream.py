"""Catalog list is ABAC-only; BYOT does not hide shared registered assets from search/list."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.data_source.asset_metadata_service import AssetMetadataService


@pytest.mark.asyncio
async def test_list_assets_does_not_filter_by_upstream_credentials():
    actor = ActorContext(tenant_id=1, user_id=2, user_role="viewer")
    service = AssetMetadataService(tenant_id=1, db_session=MagicMock())
    service.asset_repo = MagicMock()
    service.asset_repo.count_by_data_source = AsyncMock(return_value=1)
    service.asset_repo.list_by_data_source_with_search = AsyncMock(
        return_value=[
            MagicMock(
                id=1,
                data_source_id=9,
                asset_name="orders",
                asset_type="table",
                columns=[],
                row_count=1,
                source_info={},
                meta={},
                meta_override={},
                owner_id=1,
                owner_user=None,
                created_at=MagicMock(),
                updated_at=MagicMock(),
                last_metadata_synced_at=None,
                last_metadata_sync_error=None,
            )
        ]
    )
    service._ensure_data_source_access_for_actor = AsyncMock()
    service._get_resource_index_repo = MagicMock(
        return_value=MagicMock(list_by_resources=AsyncMock(return_value={}))
    )

    items, _ = await service.list_assets_for_actor(
        actor=actor,
        data_source_id=9,
        page=1,
        page_size=10,
    )

    assert len(items) == 1
    assert items[0].asset_name == "orders"
