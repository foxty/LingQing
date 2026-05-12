"""Tests for asset FTS search data-source authz pushdown."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apps.shared.data_source.service import AssetAccessScope
from apps.shared.search.search_service import SearchService


@pytest.mark.asyncio
async def test_search_assets_fts_passes_index_parent_filter():
    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.session = AsyncMock()
    service.resource_index_repo = AsyncMock()
    service.resource_index_repo.search_assets_fts = AsyncMock(return_value=[])
    service.asset_repo = AsyncMock()
    service.asset_repo.list_by_ids = AsyncMock(return_value=[])
    service.data_source_repo = AsyncMock()
    service.data_source_repo.list_by_ids = AsyncMock(return_value=[])

    index_filter = object()
    await service._search_assets_fts("query", k=5, index_abac_filter=index_filter)

    service.resource_index_repo.search_assets_fts.assert_awaited_once_with(
        tenant_id=1,
        query="query",
        limit=5,
        abac_filter=index_filter,
    )


@pytest.mark.asyncio
async def test_search_assets_hybrid_uses_separate_fts_and_asset_filters():
    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.session = AsyncMock()

    index_filter = object()
    asset_filter = object()
    service._search_assets_fts = AsyncMock(return_value=[])
    service._search_assets_vector = AsyncMock(return_value=[])

    await service._search_assets_hybrid(
        "fts query",
        "vector query",
        k=3,
        index_abac_filter=index_filter,
        asset_abac_filter=asset_filter,
    )

    service._search_assets_fts.assert_awaited_once_with("fts query", 6, index_filter)
    service._search_assets_vector.assert_awaited_once_with("vector query", 6, asset_filter)


@pytest.mark.asyncio
async def test_search_assets_uses_access_scope_filters():
    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.user_id = 2
    service.user_role = "member"
    service.session = AsyncMock()

    index_filter = object()
    asset_filter = object()
    scope = AssetAccessScope(
        deny_all=False,
        allow_all=False,
        asset_filter=asset_filter,
        index_parent_filter=index_filter,
    )
    service._get_asset_access_scope = AsyncMock(return_value=scope)
    service._search_assets_hybrid = AsyncMock(return_value=[])
    service._asset_to_item = lambda result: result

    await service.search_assets(f"query-{uuid4().hex[:6]}", page=1, page_size=10)

    service._search_assets_hybrid.assert_awaited_once()
    kwargs = service._search_assets_hybrid.await_args.kwargs
    assert kwargs["index_abac_filter"] is index_filter
    assert kwargs["asset_abac_filter"] is asset_filter


@pytest.mark.asyncio
async def test_get_resource_context_chunks_checks_asset_data_source_authz(monkeypatch):
    from apps.shared.core.exceptions import AuthorizationError
    from apps.shared.domain.types import RESOURCE_TYPE_ASSET

    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.user_id = 2
    service.user_role = "member"
    service.session = AsyncMock()
    service.rag_manager = AsyncMock()

    data_source_service = AsyncMock()
    data_source_service.require_asset_access = AsyncMock(side_effect=AuthorizationError("denied"))

    monkeypatch.setattr(
        "apps.shared.search.search_service.DataSourceService",
        lambda tenant_id, data_source_repo, asset_repo: data_source_service,
    )

    with pytest.raises(AuthorizationError):
        await service.get_resource_context_chunks(
            resource_type=RESOURCE_TYPE_ASSET,
            resource_id=99,
            chunk_index=0,
            context_range=1,
        )

    data_source_service.require_asset_access.assert_awaited_once()
    service.rag_manager.get_context_chunks_by_resource.assert_not_called()
