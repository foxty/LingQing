"""Tests for default document parser."""

from datetime import UTC, datetime

import pytest

from apps.shared.document.domain import DocumentDomain
from apps.shared.document.parsers.default import DefaultDocumentParser


class _FakeStorage:
    async def read(self, file_url: str) -> bytes:
        return b""

    async def get_local_path(self, file_url: str) -> str:
        return file_url


@pytest.mark.asyncio
async def test_default_parser_builds_blocks(monkeypatch):
    parser = DefaultDocumentParser(_FakeStorage())

    async def _fake_extract(_file_url: str, _filename: str, *, tenant_id: int) -> str:
        return "Sample extracted text"

    monkeypatch.setattr(parser._extractor, "extract_text", _fake_extract)

    doc = DocumentDomain(
        id=1,
        tenant_id=1,
        collection_id=1,
        filename="sample.pdf",
        file_url="/tmp/sample.pdf",
        file_size=10,
        file_hash="hash",
        status="processing",
        owner_id=1,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    blocks_doc = await parser.parse(doc)
    assert blocks_doc["parser"] == "default"
    assert blocks_doc["blocks"][0]["text"] == "Sample extracted text"
    assert parser.is_async is False
