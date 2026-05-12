"""Unit tests for RAGManager new functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from apps.shared.infra.rag.rag_manager import RAGManager


@pytest.fixture
def mock_rag_manager():
    """Create a RAGManager with mocked vector backend contract."""
    with patch("apps.shared.infra.rag.rag_manager.get_vector_backend") as mock_factory:
        mock_backend = MagicMock()
        mock_backend.add_records = AsyncMock()
        mock_backend.similarity_search = AsyncMock()
        mock_backend.get = AsyncMock()
        mock_backend.delete = AsyncMock()
        mock_backend.describe.return_value = {"backend": "mock-backend"}
        mock_factory.return_value = mock_backend

        manager = RAGManager(tenant_id=1)

        yield manager, mock_backend, mock_factory


def test_rag_manager_init_does_not_construct_chroma_client():
    """RAGManager() must not heartbeat Chroma; the HTTP client is lazy."""
    manager = RAGManager(tenant_id=1)
    assert manager.tenant_id == 1
    assert manager._backend.describe()["backend"] == "chroma-http"


@pytest.mark.asyncio
async def test_add_chunks(mock_rag_manager):
    """Test add_chunks method - pure vector store operation."""
    manager, mock_backend, _ = mock_rag_manager

    # Arrange - chunks should already have metadata prepared
    chunks = [
        Document(
            page_content="Test content 1",
            metadata={"vector_ref_id": "test-uuid-123", "source_type": "document", "tenant_id": 1},
        ),
        Document(
            page_content="Test content 2",
            metadata={"vector_ref_id": "test-uuid-123", "source_type": "document", "tenant_id": 1},
        ),
    ]

    # Act
    count = await manager.add_chunks(chunks)

    # Assert
    assert count == 2
    add_call_records = mock_backend.add_records.call_args[0][0]
    assert len(add_call_records) == 2
    assert add_call_records[0]["content"] == "Test content 1"
    assert add_call_records[0]["metadata"]["tenant_id"] == 1


@pytest.mark.asyncio
async def test_add_chunks_empty(mock_rag_manager):
    """Test add_chunks with empty list."""
    manager, mock_backend, _ = mock_rag_manager

    # Act
    count = await manager.add_chunks([])

    # Assert
    assert count == 0
    mock_backend.add_records.assert_not_called()


@pytest.mark.asyncio
async def test_clear_collection(mock_rag_manager):
    """Test clear_collection delegates to backend delete_collection."""
    manager, mock_backend, _ = mock_rag_manager
    mock_backend.delete_collection = AsyncMock()

    await manager.clear_collection()

    mock_backend.delete_collection.assert_called_once()
