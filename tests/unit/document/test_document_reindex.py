"""Unit tests for document re-index queue operations."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.document.service import DocumentService


@pytest.fixture
def document_service():
    service = DocumentService(tenant_id=1, db_session=AsyncMock(), file_storage=MagicMock())
    service.document_repo = AsyncMock()
    service._resource_index_repo = AsyncMock()
    service._get_resource_index_repo = MagicMock(return_value=service._resource_index_repo)
    return service


@pytest.mark.asyncio
async def test_queue_document_reindex_marks_stale(document_service):
    document_db = MagicMock()
    document_db.status = "active"
    document_service.document_repo.get_by_id_and_tenant.return_value = document_db
    document_service._resource_index_repo.mark_document_vector_stale.return_value = True
    document_service._resource_index_repo.get_by_resource.return_value = MagicMock()

    await document_service.queue_document_reindex(42)

    document_service._resource_index_repo.mark_document_vector_stale.assert_awaited_once_with(1, 42)


@pytest.mark.asyncio
async def test_queue_document_reindex_requires_parsed_content(document_service):
    document_db = MagicMock()
    document_service.document_repo.get_by_id_and_tenant.return_value = document_db
    document_service._resource_index_repo.mark_document_vector_stale.return_value = False

    with pytest.raises(ValidationError, match="parsed content"):
        await document_service.queue_document_reindex(42)


@pytest.mark.asyncio
async def test_queue_document_reindex_not_found(document_service):
    document_service.document_repo.get_by_id_and_tenant.return_value = None

    with pytest.raises(ResourceNotFoundError):
        await document_service.queue_document_reindex(99)
