"""Unit tests for ResourceIndexService vector synchronization fix.

Tests that verify _sync_single_item properly deletes old vectors before adding new ones.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.infra.rag.metadata_keys import (
    META_CHUNK_INDEX,
    META_RESOURCE_ID,
    META_RESOURCE_TYPE,
    META_TENANT_ID,
    META_TOTAL_CHUNKS,
)
from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.search.schemas import ResourceIndexPendingItem


@pytest.mark.asyncio
async def test_sync_single_item_deletes_old_vectors_before_adding_new():
    """Verify that _sync_single_item calls remove_by_resource before adding new chunks."""
    # Create mock dependencies
    mock_db_session = MagicMock()
    mock_repo = AsyncMock()  # Changed to AsyncMock since repo methods are awaited
    mock_rag_manager = AsyncMock()

    # Mock RAGManager at class level before service instantiation
    with patch("apps.shared.search.indexing_service.RAGManager", return_value=mock_rag_manager):
        # Create service instance (RAGManager will be mocked)
        service = ResourceIndexService(tenant_id=1, db_session=mock_db_session)
        service._repo = mock_repo
        # rag_manager is already mocked via patch

        # Mock parser result
        mock_parse_result = MagicMock()
        mock_parse_result.tokenized_content = "test content"
        mock_parse_result.chunks = [
            MagicMock(page_content="chunk 1", metadata={}),
            MagicMock(page_content="chunk 2", metadata={}),
        ]

        # Create pending item
        pending_item = ResourceIndexPendingItem(
            id=123,
            tenant_id=1,
            resource_type="asset",
            resource_id=456,
            raw_content={"text": "test content", "meta": {}},
            vector_retry_count=0,
            owner_id=1,
            parent_id=None,
        )

        # Patch ResourceParser
        with patch("apps.shared.search.indexing_service.ResourceParser") as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser.from_raw.return_value = mock_parse_result
            mock_parser_class.return_value = mock_parser

            # Call _sync_single_item
            result = await service._sync_single_item(pending_item)

            # Verify remove_by_resource was called BEFORE add_chunks
            assert mock_rag_manager.remove_by_resource.called
            mock_rag_manager.remove_by_resource.assert_called_once_with("asset", 456)

            # Verify add_chunks was called after removal
            assert mock_rag_manager.add_chunks.called

            # Verify the call order (remove should be before add)
            remove_call_idx = None
            add_call_idx = None
            for idx, call in enumerate(mock_rag_manager.method_calls):
                if call[0] == "remove_by_resource":
                    remove_call_idx = idx
                elif call[0] == "add_chunks":
                    add_call_idx = idx

            assert remove_call_idx is not None, "remove_by_resource was not called"
            assert add_call_idx is not None, "add_chunks was not called"
            assert remove_call_idx < add_call_idx, "remove_by_resource should be called before add_chunks"

            # Verify success
            assert result["success"] is True
            assert result["id"] == 123


@pytest.mark.asyncio
async def test_sync_single_item_handles_removal_failure_gracefully():
    """Verify that _sync_single_item continues even if removal fails."""
    # Create mock dependencies
    mock_db_session = MagicMock()
    mock_repo = AsyncMock()  # Changed to AsyncMock since it's awaited
    mock_rag_manager = AsyncMock()

    # Simulate removal failure but continue
    mock_rag_manager.remove_by_resource.side_effect = Exception("Removal failed")

    # Mock RAGManager at class level before service instantiation
    with patch("apps.shared.search.indexing_service.RAGManager", return_value=mock_rag_manager):
        # Create service instance (RAGManager will be mocked)
        service = ResourceIndexService(tenant_id=1, db_session=mock_db_session)
        service._repo = mock_repo

        # Mock parser result
        mock_parse_result = MagicMock()
        mock_parse_result.tokenized_content = "test content"
        mock_parse_result.chunks = [MagicMock(page_content="chunk 1", metadata={})]

        # Create pending item
        pending_item = ResourceIndexPendingItem(
            id=123,
            tenant_id=1,
            resource_type="asset",
            resource_id=456,
            raw_content={"text": "test content", "meta": {}},
            vector_retry_count=0,
            owner_id=1,
            parent_id=None,
        )

        # Patch ResourceParser
        with patch("apps.shared.search.indexing_service.ResourceParser") as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser.from_raw.return_value = mock_parse_result
            mock_parser_class.return_value = mock_parser

            # Call _sync_single_item - should handle exception and mark as failed
            result = await service._sync_single_item(pending_item)

            # Should fail because removal exception propagates
            assert result["success"] is False
            assert "error" in result

            # Verify update_vector_failed was called
            assert mock_repo.update_vector_failed.called


@pytest.mark.asyncio
async def test_sync_single_item_updates_repo_after_successful_sync():
    """Verify that _sync_single_item updates repo with tokenized content and hash."""
    # Create mock dependencies
    mock_db_session = MagicMock()
    mock_repo = AsyncMock()
    mock_rag_manager = AsyncMock()

    # Mock RAGManager at class level before service instantiation
    with patch("apps.shared.search.indexing_service.RAGManager", return_value=mock_rag_manager):
        # Create service instance (RAGManager will be mocked)
        service = ResourceIndexService(tenant_id=1, db_session=mock_db_session)
        service._repo = mock_repo

        # Mock parser result
        mock_parse_result = MagicMock()
        mock_parse_result.tokenized_content = "tokenized test content"
        mock_parse_result.chunks = [MagicMock(page_content="chunk 1", metadata={})]

        # Create pending item
        pending_item = ResourceIndexPendingItem(
            id=123,
            tenant_id=1,
            resource_type="asset",
            resource_id=456,
            raw_content={"text": "test content", "meta": {}},
            vector_retry_count=0,
            owner_id=1,
            parent_id=None,
        )

        # Patch ResourceParser
        with patch("apps.shared.search.indexing_service.ResourceParser") as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser.from_raw.return_value = mock_parse_result
            mock_parser_class.return_value = mock_parser

            # Call _sync_single_item
            result = await service._sync_single_item(pending_item)

            # Verify update_vector_synced was called with correct parameters
            assert mock_repo.update_vector_synced.called
            call_args = mock_repo.update_vector_synced.call_args
            assert call_args[0][0] == 123  # record_id
            assert "vector_content_hash" in call_args[1]
            assert call_args[1]["tokenized_content"] == "tokenized test content"

            # Verify success
            assert result["success"] is True


@pytest.mark.asyncio
async def test_sync_single_item_vector_metadata_includes_resource_id():
    """Synced vector chunks must expose resource_id for SearchService post-filtering."""
    mock_db_session = MagicMock()
    mock_repo = AsyncMock()
    mock_rag_manager = AsyncMock()

    with patch("apps.shared.search.indexing_service.RAGManager", return_value=mock_rag_manager):
        service = ResourceIndexService(tenant_id=1, db_session=mock_db_session)
        service._repo = mock_repo

        mock_parse_result = MagicMock()
        mock_parse_result.tokenized_content = "alpha asset content"
        mock_parse_result.chunks = [
            MagicMock(page_content="alpha asset content", metadata={"asset_name": "orders"}),
        ]

        pending_item = ResourceIndexPendingItem(
            id=123,
            tenant_id=1,
            resource_type="asset",
            resource_id=456,
            raw_content={"text": "alpha asset content", "meta": {"asset_name": "orders"}},
            vector_retry_count=0,
            owner_id=1,
            parent_id=10,
        )

        with patch("apps.shared.search.indexing_service.ResourceParser") as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser.from_raw.return_value = mock_parse_result
            mock_parser_class.return_value = mock_parser

            result = await service._sync_single_item(pending_item)

            assert result["success"] is True
            assert mock_rag_manager.add_chunks.called
            chunks = mock_rag_manager.add_chunks.call_args[0][0]
            assert len(chunks) == 1
            metadata = chunks[0].metadata
            assert metadata[META_RESOURCE_TYPE] == "asset"
            assert metadata[META_RESOURCE_ID] == 456
            assert metadata[META_TENANT_ID] == 1
            assert metadata[META_CHUNK_INDEX] == 0
            assert metadata[META_TOTAL_CHUNKS] == 1


def _pending_item(*, item_id: int = 123, raw_content: dict | None = None) -> ResourceIndexPendingItem:
    return ResourceIndexPendingItem(
        id=item_id,
        tenant_id=1,
        resource_type="document",
        resource_id=11,
        raw_content=raw_content,
        vector_retry_count=0,
        owner_id=1,
        parent_id=None,
    )


@pytest.mark.asyncio
async def test_sync_single_item_marks_failed_when_raw_content_missing():
    mock_repo = AsyncMock()
    mock_rag_manager = AsyncMock()

    with patch("apps.shared.search.indexing_service.RAGManager", return_value=mock_rag_manager):
        service = ResourceIndexService(tenant_id=2, db_session=MagicMock())
        service._repo = mock_repo

        result = await service._sync_single_item(_pending_item(raw_content=None))

    assert result == {"success": False, "id": 123, "error": "No raw_content in ResourceIndex"}
    mock_repo.update_vector_failed.assert_awaited_once()
    record_id, error, next_retry_at = mock_repo.update_vector_failed.call_args.args
    assert record_id == 123
    assert error == "No raw_content in ResourceIndex"
    assert next_retry_at is not None
    mock_rag_manager.add_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_sync_all_pending_stops_when_same_item_is_returned():
    mock_repo = AsyncMock()
    mock_rag_manager = AsyncMock()
    stuck_item = _pending_item(raw_content=None)

    with patch("apps.shared.search.indexing_service.RAGManager", return_value=mock_rag_manager):
        service = ResourceIndexService(tenant_id=2, db_session=MagicMock())
        service._repo = mock_repo
        service.list_pending_items = AsyncMock(return_value=[stuck_item])

        result = await service.sync_all_pending(batch_size=50)

    assert result["total_failed"] == 1
    assert result["total_synced"] == 0
    assert result["batches_processed"] == 2
    assert service.list_pending_items.await_count == 2
