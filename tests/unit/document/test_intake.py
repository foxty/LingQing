"""Tests for DocumentIntake pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from apps.shared.core.exceptions import DuplicateResourceError
from apps.shared.document.intake import DocumentIntake, IntakeRequest


@pytest.fixture
def intake() -> DocumentIntake:
    return DocumentIntake(
        tenant_id=1,
        db_session=AsyncMock(),
        file_storage=AsyncMock(),
    )


def test_duplicate_content_message_different_filenames():
    message = DocumentIntake.duplicate_content_message(
        "2026-Peak-Season-Readiness.pptx",
        "2026 Website Performance Test Report.pptx",
        upload_date=datetime(2026, 9, 26, 11, 52, 52, tzinfo=UTC),
    )
    assert "2026-Peak-Season-Readiness.pptx" in message
    assert "2026 Website Performance Test Report.pptx" in message
    assert "内容相同" in message


def test_duplicate_content_message_same_filename():
    message = DocumentIntake.duplicate_content_message("report.pdf", "report.pdf")
    assert message == "该集合中已存在相同内容的文件 'report.pdf'。"


@pytest.mark.asyncio
async def test_persist_raises_on_duplicate(intake: DocumentIntake):
    existing = MagicMock()
    existing.id = 99
    existing.filename = "existing.pdf"
    existing.upload_date = datetime.now(UTC)
    intake._document_repo.find_by_hash = AsyncMock(return_value=existing)

    with pytest.raises(DuplicateResourceError):
        await intake.persist(
            IntakeRequest(
                collection_id=10,
                filename="upload.pdf",
                content=b"duplicate-content",
                owner_id=7,
            )
        )


@pytest.mark.asyncio
async def test_persist_skips_duplicate_when_configured(intake: DocumentIntake):
    existing = MagicMock()
    existing.id = 99
    existing.filename = "existing.pdf"
    existing.status = "active"
    existing.upload_date = datetime.now(UTC)
    existing.created_at = datetime.now(UTC)
    existing.updated_at = datetime.now(UTC)
    existing.tenant_id = 1
    existing.collection_id = 10
    existing.file_url = "documents/1/existing.pdf"
    existing.file_size = 64
    existing.file_hash = "abc"
    existing.owner_id = 7
    intake._document_repo.find_by_hash = AsyncMock(return_value=existing)
    intake._resource_index_repo.get_by_resource = AsyncMock(return_value=None)

    doc = await intake.persist(
        IntakeRequest(
            collection_id=10,
            filename="upload.pdf",
            content=b"duplicate-content",
            owner_id=7,
            on_duplicate="skip",
        )
    )

    assert doc.id == 99
    intake.file_storage.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_registers_document_for_parse(intake: DocumentIntake, monkeypatch):
    intake._document_repo.find_by_hash = AsyncMock(return_value=None)
    intake.file_storage.save = AsyncMock(return_value="documents/1/report.pdf")
    intake.file_storage.get_size = AsyncMock(return_value=256)

    created_db = MagicMock()
    created_db.id = 42
    created_db.tenant_id = 1
    created_db.collection_id = 10
    created_db.filename = "report.pdf"
    created_db.file_url = "documents/1/report.pdf"
    created_db.file_size = 256
    created_db.file_hash = DocumentIntake.calculate_file_hash(b"hello")
    created_db.status = "processing"
    created_db.owner_id = 7
    created_db.upload_date = datetime.now(UTC)
    created_db.created_at = datetime.now(UTC)
    created_db.updated_at = datetime.now(UTC)

    intake._document_repo.create_document = AsyncMock(return_value=created_db)
    intake._document_repo.get_by_id_and_tenant = AsyncMock(return_value=created_db)
    intake._document_repo.update_status = AsyncMock()
    intake._resource_index_repo.get_by_resource = AsyncMock(return_value=None)

    register_mock = AsyncMock()
    monkeypatch.setattr(intake, "_register_for_parse", register_mock)

    doc = await intake.persist(
        IntakeRequest(
            collection_id=10,
            filename="report.pdf",
            content=b"hello",
            owner_id=7,
            source="upload",
        )
    )

    assert doc.id == 42
    register_mock.assert_awaited_once()
    intake.file_storage.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_maps_integrity_error_to_duplicate(intake: DocumentIntake):
    intake._document_repo.find_by_hash = AsyncMock(return_value=None)
    intake.file_storage.save = AsyncMock(return_value="documents/1/report.pdf")
    intake.file_storage.get_size = AsyncMock(return_value=256)
    intake._document_repo.create_document = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))

    with pytest.raises(DuplicateResourceError):
        await intake.persist(
            IntakeRequest(
                collection_id=10,
                filename="report.pdf",
                content=b"hello",
                owner_id=7,
            )
        )
