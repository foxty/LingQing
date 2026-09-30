"""Tests for Drive sync update paths and reparse storage safety."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.document.intake import DocumentIntake
from apps.shared.document.manifest import write_blocks_json
from apps.shared.document.parse_pipeline import DocumentParsePipeline
from apps.shared.document.sync_service import DocumentSyncService, SyncDiffResult
from apps.shared.infra.external_files.port import ExternalFileEntry
from apps.shared.infra.storage.file_storage import LocalFileStorage


def _entry(external_id: str, *, modified_at: datetime) -> ExternalFileEntry:
    return ExternalFileEntry(
        external_id=external_id,
        name=f"{external_id}.pdf",
        mime_type="application/pdf",
        modified_at=modified_at,
    )


@pytest.fixture
def sync_service() -> DocumentSyncService:
    service = DocumentSyncService(
        tenant_id=1,
        db_session=AsyncMock(),
        file_storage=AsyncMock(),
    )
    service._sync_repo = AsyncMock()
    service._document_repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_update_existing_document_skips_when_hash_and_filename_match(sync_service: DocumentSyncService):
    content = b"unchanged-bytes"
    file_hash = DocumentIntake.calculate_file_hash(content)
    remote = _entry("file-a", modified_at=datetime(2026, 2, 1, tzinfo=UTC))
    document_db = SimpleNamespace(
        id=10,
        file_hash=file_hash,
        filename="file-a.pdf",
        file_url="10/original/file-a.pdf",
    )
    sync_service._document_repo.get_by_id_and_tenant = AsyncMock(return_value=document_db)
    drive_client = AsyncMock()
    drive_client.download_file = AsyncMock(return_value=("file-a.pdf", content))
    parse_pipeline = AsyncMock()

    updated = await sync_service._update_existing_document(
        parse_pipeline=parse_pipeline,
        document_id=10,
        drive_client=drive_client,
        remote=remote,
    )

    assert updated is False
    parse_pipeline.queue_document_reparse.assert_not_awaited()
    sync_service.file_storage.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_existing_document_replaces_file_and_queues_reparse(sync_service: DocumentSyncService):
    old_hash = DocumentIntake.calculate_file_hash(b"old")
    new_content = b"new-bytes"
    remote = _entry("file-a", modified_at=datetime(2026, 2, 1, tzinfo=UTC))
    document_db = SimpleNamespace(
        id=10,
        file_hash=old_hash,
        filename="file-a.pdf",
        file_url="10/original/file-a.pdf",
    )
    sync_service._document_repo.get_by_id_and_tenant = AsyncMock(return_value=document_db)
    sync_service.file_storage.save = AsyncMock(return_value="documents/1/10/original/file-a.pdf")
    sync_service.file_storage.get_size = AsyncMock(return_value=len(new_content))
    sync_service.file_storage.delete = AsyncMock(return_value=True)
    sync_service._document_repo.update_document_file = AsyncMock()
    drive_client = AsyncMock()
    drive_client.download_file = AsyncMock(return_value=("file-a.pdf", new_content))
    parse_pipeline = AsyncMock()

    updated = await sync_service._update_existing_document(
        parse_pipeline=parse_pipeline,
        document_id=10,
        drive_client=drive_client,
        remote=remote,
    )

    assert updated is True
    sync_service._document_repo.update_document_file.assert_awaited_once()
    sync_service.file_storage.delete.assert_awaited_once()
    parse_pipeline.queue_document_reparse.assert_awaited_once_with(10, triggered_by="drive_sync")


@pytest.mark.asyncio
async def test_apply_sync_diff_skips_download_when_timestamp_unchanged(sync_service: DocumentSyncService):
    modified_at = datetime(2026, 1, 1, tzinfo=UTC)
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=10,
        external_modified_at=modified_at,
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])
    drive_client = AsyncMock()

    with patch("apps.shared.document.sync_service.DocumentParsePipeline"):
        result = await sync_service._apply_sync_diff(
            connector=MagicMock(id=5, collection_id=20),
            connection=MagicMock(owner_id=7),
            drive_client=drive_client,
            remote_files=[_entry("file-a", modified_at=modified_at)],
        )

    assert result == SyncDiffResult(added=0, updated=0, deleted=0, skipped=1)
    drive_client.download_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_sync_diff_skips_update_when_hash_unchanged_after_timestamp_change(
    sync_service: DocumentSyncService,
):
    content = b"same-content"
    file_hash = DocumentIntake.calculate_file_hash(content)
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=10,
        external_modified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])
    sync_service._document_is_deleted = AsyncMock(return_value=False)
    sync_service._document_repo.get_by_id_and_tenant = AsyncMock(
        return_value=SimpleNamespace(
            id=10,
            file_hash=file_hash,
            filename="file-a.pdf",
            file_url="10/original/file-a.pdf",
        )
    )
    sync_service._sync_repo.update_external_file = AsyncMock()
    drive_client = AsyncMock()
    drive_client.download_file = AsyncMock(return_value=("file-a.pdf", content))
    parse_pipeline = AsyncMock()

    with patch(
        "apps.shared.document.sync_service.DocumentParsePipeline",
        return_value=parse_pipeline,
    ):
        result = await sync_service._apply_sync_diff(
            connector=MagicMock(id=5, collection_id=20),
            connection=MagicMock(owner_id=7),
            drive_client=drive_client,
            remote_files=[_entry("file-a", modified_at=datetime(2026, 2, 1, tzinfo=UTC))],
        )

    assert result == SyncDiffResult(added=0, updated=0, deleted=0, skipped=1)
    drive_client.download_file.assert_awaited_once()
    parse_pipeline.queue_document_reparse.assert_not_awaited()
    sync_service._sync_repo.update_external_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_sync_diff_logs_skip_unchanged(sync_service: DocumentSyncService, caplog):
    modified_at = datetime(2026, 1, 1, tzinfo=UTC)
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=10,
        external_modified_at=modified_at,
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])

    with patch("apps.shared.document.sync_service.DocumentParsePipeline"):
        with caplog.at_level("INFO"):
            await sync_service._apply_sync_diff(
                connector=MagicMock(id=5, collection_id=20),
                connection=MagicMock(owner_id=7),
                drive_client=AsyncMock(),
                remote_files=[_entry("file-a", modified_at=modified_at)],
            )

    assert "document_sync_skip_unchanged" in caplog.text
    assert "document_sync_diff" in caplog.text


@pytest.mark.asyncio
async def test_apply_sync_diff_logs_hash_match_skip(sync_service: DocumentSyncService, caplog):
    content = b"same-content"
    file_hash = DocumentIntake.calculate_file_hash(content)
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=10,
        external_modified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])
    sync_service._document_is_deleted = AsyncMock(return_value=False)
    sync_service._document_repo.get_by_id_and_tenant = AsyncMock(
        return_value=SimpleNamespace(
            id=10,
            file_hash=file_hash,
            filename="file-a.pdf",
            file_url="10/original/file-a.pdf",
        )
    )
    sync_service._sync_repo.update_external_file = AsyncMock()
    drive_client = AsyncMock()
    drive_client.download_file = AsyncMock(return_value=("file-a.pdf", content))

    with patch("apps.shared.document.sync_service.DocumentParsePipeline", return_value=AsyncMock()):
        with caplog.at_level("INFO"):
            await sync_service._apply_sync_diff(
                connector=MagicMock(id=5, collection_id=20),
                connection=MagicMock(owner_id=7),
                drive_client=drive_client,
                remote_files=[_entry("file-a", modified_at=datetime(2026, 2, 1, tzinfo=UTC))],
            )

    assert "document_sync_download" in caplog.text
    assert "document_sync_skip_hash_match" in caplog.text


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
async def test_queue_document_reparse_preserves_original_file(tenant_docs_root):
    storage = LocalFileStorage()
    doc_id = 42
    original_file = tenant_docs_root / str(doc_id) / "original" / "report.docx"
    original_file.parent.mkdir(parents=True, exist_ok=True)
    original_bytes = b"source bytes for reparse"
    original_file.write_bytes(original_bytes)

    blocks_doc = {"schema_version": 1, "parser": "docling", "blocks": [{"type": "text", "text": "hello"}]}
    storage_uri = await write_blocks_json(
        storage,
        tenant_id=1,
        document_id=doc_id,
        blocks_document=blocks_doc,
    )

    now = datetime.now(UTC)
    document_db = SimpleNamespace(
        id=doc_id,
        tenant_id=1,
        collection_id=1,
        filename="report.docx",
        file_url=f"{doc_id}/original/report.docx",
        file_size=len(original_bytes),
        file_hash="abc",
        status="active",
        owner_id=1,
        upload_date=now,
        created_at=now,
        updated_at=now,
        owner_user=None,
    )
    resource_index = SimpleNamespace(
        raw_content={"schema_version": 1, "storage_uri": storage_uri},
    )

    pipeline = DocumentParsePipeline(tenant_id=1, db_session=AsyncMock(), file_storage=storage)
    pipeline._document_repo.get_by_id_and_tenant = AsyncMock(return_value=document_db)
    pipeline._resource_index_repo.get_by_resource = AsyncMock(return_value=resource_index)
    pipeline._resource_index_repo.reset_parse_state = AsyncMock()
    pipeline.enqueue_document_parse = AsyncMock()

    await pipeline.queue_document_reparse(doc_id, triggered_by="drive_sync")

    assert original_file.exists()
    assert original_file.read_bytes() == original_bytes
    assert not (tenant_docs_root / str(doc_id) / "parsed").exists()
    pipeline.enqueue_document_parse.assert_awaited_once()
