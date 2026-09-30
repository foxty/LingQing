"""Tests for document delete storage and index cleanup."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.document.domain import DocumentDomain, DocumentStatus
from apps.shared.document.manifest import blocks_relative_key, delete_parsed_artifacts, write_blocks_json
from apps.shared.infra.storage.file_storage import LocalFileStorage


@pytest.fixture
def tenant_docs_root(tmp_path, monkeypatch):
    docs_root = tmp_path / "tenants" / "tenant_1" / "documents"
    docs_root.mkdir(parents=True)

    def _get_tenant_documents_path(tenant_id: int | str) -> str:
        root = tmp_path / "tenants" / f"tenant_{tenant_id}" / "documents"
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

    monkeypatch.setattr("apps.shared.document.manifest.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.shared.infra.storage.paths.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.config.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.config.EnvConfig.DATA_ROOT_PATH", str(tmp_path))
    return docs_root


@pytest.mark.asyncio
async def test_delete_parsed_artifacts_removes_parsed_directory_but_preserves_original(tenant_docs_root):
    storage = LocalFileStorage()
    blocks_doc = {"schema_version": 1, "parser": "docling", "blocks": [{"type": "text", "text": "hello"}]}
    storage_uri = await write_blocks_json(
        storage,
        tenant_id=1,
        document_id=42,
        blocks_document=blocks_doc,
    )
    doc_dir = tenant_docs_root / "42"
    original_file = doc_dir / "original" / "report.docx"
    original_file.parent.mkdir(parents=True, exist_ok=True)
    original_file.write_bytes(b"source bytes")
    assert (doc_dir / "parsed" / "latest" / "blocks.json").exists()

    await delete_parsed_artifacts(
        storage,
        tenant_id=1,
        document_id=42,
        storage_uri=storage_uri,
    )

    assert doc_dir.exists()
    assert not (doc_dir / "parsed").exists()
    assert original_file.exists()
    assert original_file.read_bytes() == b"source bytes"


@pytest.mark.asyncio
async def test_delete_parsed_artifacts_without_storage_uri_uses_default_path(tenant_docs_root):
    storage = LocalFileStorage()
    relative_key = blocks_relative_key(99)
    target = tenant_docs_root / relative_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"parser": "default", "blocks": []}), encoding="utf-8")
    original_file = tenant_docs_root / "99" / "original" / "report.pdf"
    original_file.parent.mkdir(parents=True, exist_ok=True)
    original_file.write_bytes(b"source bytes")

    await delete_parsed_artifacts(
        storage,
        tenant_id=1,
        document_id=99,
        storage_uri=None,
    )

    assert not (tenant_docs_root / "99" / "parsed").exists()
    assert original_file.exists()


@pytest.mark.asyncio
async def test_delete_documents_invokes_parsed_and_index_cleanup(monkeypatch):
    from apps.shared.document.service import DocumentService

    file_storage = MagicMock()
    file_storage.delete = AsyncMock(return_value=True)

    deleted_parsed: list[int] = []

    async def _delete_parsed_artifacts(_storage, *, tenant_id, document_id, storage_uri=None):
        deleted_parsed.append(document_id)

    monkeypatch.setattr("apps.shared.document.manifest.delete_parsed_artifacts", _delete_parsed_artifacts)

    document_db = MagicMock()
    document_db.collection_id = 1
    document_db.id = 7

    document_domain = DocumentDomain(
        id=7,
        tenant_id=1,
        collection_id=1,
        owner_id=1,
        filename="sample.pdf",
        file_url="7/original/sample.pdf",
        file_size=10,
        file_hash="abc",
        status=DocumentStatus.ACTIVE,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    resource_index = MagicMock()
    resource_index.raw_content = {
        "schema_version": 1,
        "storage_uri": "7/parsed/latest/blocks.json",
    }

    service = DocumentService(tenant_id=1, db_session=AsyncMock(), file_storage=file_storage)
    service.document_repo.get_by_id_and_tenant = AsyncMock(return_value=document_db)
    service.document_repo.delete_document = AsyncMock(return_value=True)
    service._collection_service.require_collection_access = AsyncMock()
    service._get_resource_index_repo = MagicMock(
        return_value=MagicMock(get_by_resource=AsyncMock(return_value=resource_index))
    )
    service._delete_document_resource_index = AsyncMock()

    monkeypatch.setattr(
        "apps.shared.document.service.db_document_to_domain",
        lambda _db, _index=None: document_domain,
    )

    result = await service.delete_documents([7], requester_id=1, requester_role="admin")

    assert result["deleted_count"] == 1
    assert deleted_parsed == [7]
    file_storage.delete.assert_awaited_once()
    deleted_path = file_storage.delete.await_args.args[0]
    assert deleted_path.endswith("7/original/sample.pdf")
    service._delete_document_resource_index.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_delete_documents_removes_original_and_parsed_tree_on_disk(tenant_docs_root, monkeypatch):
    from apps.shared.document.service import DocumentService

    storage = LocalFileStorage()
    original_path = tenant_docs_root / "7" / "original" / "sample.pdf"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(b"sample")
    parsed_path = tenant_docs_root / "7" / "parsed" / "latest" / "blocks.json"
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text('{"blocks": []}', encoding="utf-8")

    document_db = MagicMock()
    document_db.collection_id = 1
    document_db.id = 7

    document_domain = DocumentDomain(
        id=7,
        tenant_id=1,
        collection_id=1,
        owner_id=1,
        filename="sample.pdf",
        file_url="7/original/sample.pdf",
        file_size=6,
        file_hash="abc",
        status=DocumentStatus.ACTIVE,
        upload_date=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    resource_index = MagicMock()
    resource_index.raw_content = {
        "schema_version": 1,
        "storage_uri": "7/parsed/latest/blocks.json",
    }

    service = DocumentService(tenant_id=1, db_session=AsyncMock(), file_storage=storage)
    service.document_repo.get_by_id_and_tenant = AsyncMock(return_value=document_db)
    service.document_repo.delete_document = AsyncMock(return_value=True)
    service._collection_service.require_collection_access = AsyncMock()
    service._get_resource_index_repo = MagicMock(
        return_value=MagicMock(get_by_resource=AsyncMock(return_value=resource_index))
    )
    service._delete_document_resource_index = AsyncMock()
    monkeypatch.setattr(
        "apps.shared.document.service.db_document_to_domain",
        lambda _db, _index=None: document_domain,
    )

    result = await service.delete_documents([7], requester_id=1, requester_role="admin")

    assert result["deleted_count"] == 1
    assert not (tenant_docs_root / "7").exists()
