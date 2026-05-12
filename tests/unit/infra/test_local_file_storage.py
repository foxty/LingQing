"""Tests for local file storage."""

from io import BytesIO

import pytest

from apps.shared.infra.storage.file_storage import LocalFileStorage


@pytest.mark.asyncio
async def test_save_creates_nested_directories(monkeypatch, tmp_path):
    tenant_docs = tmp_path / "tenant_2" / "documents"
    monkeypatch.setattr(
        "apps.shared.infra.storage.file_storage.get_tenant_documents_path",
        lambda tenant_id: str(tenant_docs),
    )

    storage = LocalFileStorage()
    relative_key = "5/parsed/latest/blocks.json"
    storage_key = await storage.save("2", relative_key, BytesIO(b'{"blocks": []}'))

    saved_path = tenant_docs / relative_key
    assert storage_key == relative_key
    assert saved_path.exists()
    assert saved_path.read_bytes() == b'{"blocks": []}'
