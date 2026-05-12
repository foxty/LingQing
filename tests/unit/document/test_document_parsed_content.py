from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.document.service import PARSED_CONTENT_BLOCK_LIMIT, DocumentService


def _service() -> DocumentService:
    service = DocumentService(tenant_id=1, db_session=MagicMock(), file_storage=MagicMock())
    service.document_repo = MagicMock()
    service._collection_service = MagicMock()
    service._collection_service.require_collection_access = AsyncMock()
    service._resource_index_repo = MagicMock()
    return service


def _document_db(*, document_id: int = 11, filename: str = "spec.pdf"):
    row = MagicMock()
    row.id = document_id
    row.collection_id = 4
    row.filename = filename
    return row


@pytest.mark.asyncio
async def test_get_parsed_content_missing_document():
    service = _service()
    service.document_repo.get_by_id_and_tenant = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await service.get_parsed_content(11, requester_id=2, requester_role="admin")


@pytest.mark.asyncio
async def test_get_parsed_content_without_blocks_returns_empty():
    service = _service()
    service.document_repo.get_by_id_and_tenant = AsyncMock(return_value=_document_db())
    index = MagicMock()
    index.parsed_at = None
    index.parse_error = "Docling task not found"
    index.source_parser = "docling"
    index.raw_content = None
    service._resource_index_repo.get_by_resource = AsyncMock(return_value=index)

    result = await service.get_parsed_content(11, requester_id=2, requester_role="admin")

    assert result.document_id == 11
    assert result.filename == "spec.pdf"
    assert result.parse_error == "Docling task not found"
    assert result.blocks == []
    assert result.block_count == 0
    service._collection_service.require_collection_access.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_parsed_content_returns_capped_blocks(monkeypatch):
    service = _service()
    service.document_repo.get_by_id_and_tenant = AsyncMock(return_value=_document_db())
    index = MagicMock()
    index.parsed_at = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    index.parse_error = None
    index.source_parser = "docling"
    index.raw_content = {"schema_version": 1, "storage_uri": "1/11/parsed/latest/blocks.json"}
    service._resource_index_repo.get_by_resource = AsyncMock(return_value=index)

    raw_blocks = [{"type": "text", "text": f"b{i}", "uri": "skip-me"} for i in range(PARSED_CONTENT_BLOCK_LIMIT + 5)]
    monkeypatch.setattr(
        "apps.shared.document.service.read_blocks_json",
        AsyncMock(return_value={"schema_version": 1, "parser": "docling", "blocks": raw_blocks}),
    )

    result = await service.get_parsed_content(11, requester_id=2, requester_role="member")

    assert result.truncated is True
    assert result.block_count == PARSED_CONTENT_BLOCK_LIMIT + 5
    assert len(result.blocks) == PARSED_CONTENT_BLOCK_LIMIT
    assert result.blocks[0].text == "b0"
    assert result.blocks[0].uri is None
    assert result.parser == "docling"
    assert result.parsed_at is not None
