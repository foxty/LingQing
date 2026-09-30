"""Integration-style tests for DocumentIntake with LocalFileStorage."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.document.intake import DocumentIntake, IntakeRequest
from apps.shared.infra.storage.file_storage import LocalFileStorage


@pytest.fixture
def tenant_docs_root(tmp_path, monkeypatch):
    docs_root = tmp_path / "tenants" / "tenant_1" / "documents"
    docs_root.mkdir(parents=True)

    def _get_tenant_documents_path(tenant_id: int | str) -> str:
        root = tmp_path / "tenants" / f"tenant_{tenant_id}" / "documents"
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

    monkeypatch.setattr("apps.shared.infra.storage.file_storage.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.shared.infra.storage.paths.get_tenant_documents_path", _get_tenant_documents_path)
    monkeypatch.setattr("apps.config.get_tenant_documents_path", _get_tenant_documents_path)
    return docs_root


@pytest.mark.asyncio
async def test_persist_writes_original_file_under_doc_id_on_disk(tenant_docs_root, monkeypatch):
    storage = LocalFileStorage()
    intake = DocumentIntake(tenant_id=1, db_session=AsyncMock(), file_storage=storage)
    intake._document_repo.find_by_hash = AsyncMock(return_value=None)

    created_db = MagicMock()
    created_db.id = 42
    created_db.tenant_id = 1
    created_db.collection_id = 10
    created_db.filename = "report.pdf"
    created_db.file_url = "42/original/report.pdf"
    created_db.file_size = 5
    created_db.file_hash = DocumentIntake.calculate_file_hash(b"hello")
    created_db.status = "processing"
    created_db.owner_id = 7
    created_db.upload_date = datetime.now(UTC)
    created_db.created_at = datetime.now(UTC)
    created_db.updated_at = datetime.now(UTC)

    intake._document_repo.create_document = AsyncMock(return_value=created_db)
    intake._document_repo.update_document_file = AsyncMock(return_value=created_db)
    intake._document_repo.get_by_id_and_tenant = AsyncMock(return_value=created_db)
    intake._resource_index_repo.get_by_resource = AsyncMock(return_value=None)
    monkeypatch.setattr(intake, "_register_for_parse", AsyncMock())

    await intake.persist(
        IntakeRequest(
            collection_id=10,
            filename="report.pdf",
            content=b"hello",
            owner_id=7,
        )
    )

    saved_path = tenant_docs_root / "42" / "original" / "report.pdf"
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"hello"
    assert not (tenant_docs_root / "report.pdf").exists()


@pytest.mark.asyncio
async def test_persist_does_not_create_title_folders_for_gemini_filename(tenant_docs_root, monkeypatch):
    storage = LocalFileStorage()
    intake = DocumentIntake(tenant_id=1, db_session=AsyncMock(), file_storage=storage)
    intake._document_repo.find_by_hash = AsyncMock(return_value=None)

    gemini_raw = "Peak Season Review - 2026/08/06 12:56 HKT - Notes by Gemini.docx"
    stored_filename = "Peak Season Review - 2026 - 08 - 06 12:56 HKT - Notes by Gemini.docx"

    created_db = MagicMock()
    created_db.id = 8
    created_db.tenant_id = 1
    created_db.collection_id = 10
    created_db.filename = stored_filename
    created_db.file_url = f"8/original/{stored_filename}"
    created_db.file_size = 9
    created_db.file_hash = DocumentIntake.calculate_file_hash(b"notes-body")
    created_db.status = "processing"
    created_db.owner_id = 7
    created_db.upload_date = datetime.now(UTC)
    created_db.created_at = datetime.now(UTC)
    created_db.updated_at = datetime.now(UTC)

    intake._document_repo.create_document = AsyncMock(return_value=created_db)
    intake._document_repo.update_document_file = AsyncMock(return_value=created_db)
    intake._document_repo.get_by_id_and_tenant = AsyncMock(return_value=created_db)
    intake._resource_index_repo.get_by_resource = AsyncMock(return_value=None)
    monkeypatch.setattr(intake, "_register_for_parse", AsyncMock())

    await intake.persist(
        IntakeRequest(
            collection_id=10,
            filename=gemini_raw,
            content=b"notes-body",
            owner_id=7,
        )
    )

    saved_path = tenant_docs_root / "8" / "original" / stored_filename
    assert saved_path.exists()
    assert not (tenant_docs_root / "Peak Season Review - 2026").exists()
