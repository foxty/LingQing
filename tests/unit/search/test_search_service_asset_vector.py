"""Tests for asset vector search metadata handling."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.documents import Document

from apps.shared.infra.rag.metadata_keys import META_RESOURCE_ID, META_RESOURCE_TYPE
from apps.shared.search.search_service import SearchService

_NOW = datetime.now(UTC)
_TEST_ASSET_ID = 42
_TEST_DATA_SOURCE_ID = 7
_TEST_TENANT_ID = 2
_TEST_ASSET_NAME = f"test_schema.orders_{uuid4().hex[:8]}"
_TEST_DATA_SOURCE_NAME = f"test_ds_{uuid4().hex[:8]}"
_TEST_CHUNK_TEXT = "sample orders table for integration testing"
_TEST_QUERY = "orders"


def _build_asset_db(*, asset_id: int = _TEST_ASSET_ID, asset_name: str = _TEST_ASSET_NAME):
    return SimpleNamespace(
        id=asset_id,
        data_source_id=_TEST_DATA_SOURCE_ID,
        asset_name=asset_name,
        asset_type="table",
        columns=[],
        row_count=100,
        meta={},
        meta_override={},
        source_info={},
        created_at=_NOW,
        updated_at=_NOW,
        owner_id=1,
        owner_user=None,
        last_metadata_synced_at=None,
        last_metadata_sync_error=None,
    )


@pytest.mark.asyncio
async def test_search_assets_vector_uses_resource_id_metadata():
    """Asset vector hits must resolve via resource_id (indexed key), not asset_id."""
    service = SearchService.__new__(SearchService)
    service.tenant_id = _TEST_TENANT_ID
    service.rag_manager = AsyncMock()
    service.asset_repo = AsyncMock()
    service.data_source_repo = AsyncMock()

    service.rag_manager.retrieve = AsyncMock(
        return_value=[
            Document(
                page_content=_TEST_CHUNK_TEXT,
                metadata={
                    META_RESOURCE_TYPE: "asset",
                    META_RESOURCE_ID: _TEST_ASSET_ID,
                    "tenant_id": _TEST_TENANT_ID,
                },
            )
        ]
    )

    service.asset_repo.list_by_ids = AsyncMock(return_value=[_build_asset_db()])
    service.data_source_repo.list_by_ids = AsyncMock(
        return_value=[
            SimpleNamespace(id=_TEST_DATA_SOURCE_ID, name=_TEST_DATA_SOURCE_NAME, type="table")
        ]
    )

    results = await service._search_assets_vector(_TEST_QUERY, k=5)

    assert len(results) == 1
    assert results[0].asset_id == _TEST_ASSET_ID
    assert results[0].source == "vector"


@pytest.mark.asyncio
async def test_search_assets_vector_ignores_legacy_asset_id_only_metadata():
    """Chunks with asset_id but no resource_id should not produce results."""
    service = SearchService.__new__(SearchService)
    service.tenant_id = _TEST_TENANT_ID
    service.rag_manager = AsyncMock()
    service.asset_repo = AsyncMock()
    service.data_source_repo = AsyncMock()

    service.rag_manager.retrieve = AsyncMock(
        return_value=[
            Document(
                page_content="legacy chunk",
                metadata={
                    "asset_id": _TEST_ASSET_ID,
                    META_RESOURCE_TYPE: "asset",
                    "tenant_id": _TEST_TENANT_ID,
                },
            )
        ]
    )

    results = await service._search_assets_vector(_TEST_QUERY, k=5)

    assert results == []
    service.asset_repo.list_by_ids.assert_not_called()
