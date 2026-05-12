"""Tests for DocumentProcessingService async parse orchestration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.document.domain import DocumentDomain
from apps.shared.document.parsers.base import ParseSubmission
from apps.shared.document.processing_service import DocumentProcessingService
from apps.shared.document.types import DocumentProcessOutcome, DocumentStatus, PollJobOutcome


class _FakeAsyncParser:
    name = "docling"

    def __init__(self, *, poll_status: str = "completed"):
        self.poll_status = poll_status
        self.blocks = {
            "schema_version": 1,
            "parser": "docling",
            "blocks": [{"type": "text", "text": "parsed body"}],
        }

    @property
    def is_async(self) -> bool:
        return True

    async def parse(self, document: DocumentDomain) -> dict:
        return self.blocks

    async def submit(self, document: DocumentDomain) -> ParseSubmission:
        return ParseSubmission(job_id="docling-job-1")

    async def poll(self, job_id: str) -> str:
        return self.poll_status

    async def fetch_result(self, document: DocumentDomain, job_id: str) -> dict:
        return self.blocks


class _FakeRegistry:
    def __init__(self, parser: _FakeAsyncParser):
        self._parser = parser

    def get(self, parser_name: str | None = None) -> _FakeAsyncParser:
        return self._parser

    def configured_parser_name(self) -> str:
        return self._parser.name


def _sample_doc() -> DocumentDomain:
    now = datetime.now(UTC)
    return DocumentDomain(
        id=42,
        tenant_id=1,
        collection_id=1,
        filename="report.docx",
        file_url="42/original/report.docx",
        file_size=100,
        file_hash="abc",
        status=DocumentStatus.PROCESSING,
        owner_id=1,
        upload_date=now,
        created_at=now,
        updated_at=now,
    )


def _pending_job_record(*, resource_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(
        source_parser="docling",
        parse_job_id="docling-job-1",
        resource_id=resource_id,
        parsed_at=None,
    )


def _document_db(*, doc_id: int = 42) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=doc_id,
        tenant_id=1,
        collection_id=1,
        filename="report.docx",
        file_url="42/original/report.docx",
        file_size=100,
        file_hash="abc",
        status=DocumentStatus.PROCESSING.value,
        owner_id=1,
        upload_date=now,
        created_at=now,
        updated_at=now,
        owner_user=None,
    )


@pytest.fixture
def processing_service() -> DocumentProcessingService:
    file_storage = AsyncMock()
    file_storage.exists = AsyncMock(return_value=False)
    service = DocumentProcessingService(
        tenant_id=1,
        db_session=AsyncMock(),
        file_storage=file_storage,
    )
    service._document_repo = AsyncMock()
    service._resource_index_repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_poll_one_job_completes_async_parser(processing_service, monkeypatch):
    parser = _FakeAsyncParser()
    processing_service._registry = _FakeRegistry(parser)
    processing_service._resource_index_repo.get_by_resource = AsyncMock(return_value=_pending_job_record())
    processing_service._document_repo.get_by_id = AsyncMock(return_value=_document_db())
    processing_service._document_repo.update_status = AsyncMock()
    processing_service._resource_index_repo.update_parse_completed = AsyncMock()

    persist = AsyncMock()
    monkeypatch.setattr(processing_service, "_persist_blocks", persist)

    result = await processing_service.poll_one_job(42)

    assert result == PollJobOutcome.COMPLETED
    persist.assert_awaited_once()
    processing_service._document_repo.update_status.assert_awaited_with(42, DocumentStatus.ACTIVE)


@pytest.mark.asyncio
async def test_poll_one_job_marks_failed_on_async_failure(processing_service):
    parser = _FakeAsyncParser(poll_status="failed")
    processing_service._registry = _FakeRegistry(parser)
    processing_service._resource_index_repo.get_by_resource = AsyncMock(return_value=_pending_job_record())
    processing_service._document_repo.get_by_id = AsyncMock(return_value=_document_db())
    processing_service._document_repo.update_status = AsyncMock()
    processing_service._resource_index_repo.update_parse_failed = AsyncMock()

    result = await processing_service.poll_one_job(42)

    assert result == PollJobOutcome.FAILED
    processing_service._document_repo.update_status.assert_awaited_with(42, DocumentStatus.FAILED)
    processing_service._resource_index_repo.update_parse_failed.assert_awaited_once()
    error = processing_service._resource_index_repo.update_parse_failed.await_args.kwargs["error"]
    assert error == "Async parse job failed: failed"


@pytest.mark.asyncio
async def test_process_document_submits_async_parser(processing_service):
    parser = _FakeAsyncParser()
    processing_service._registry = _FakeRegistry(parser)
    processing_service._document_repo.update_status = AsyncMock()
    processing_service._resource_index_repo.update_parse_submitted = AsyncMock()

    result = await processing_service.process_document(_sample_doc())

    assert result == DocumentProcessOutcome.SUBMITTED
    processing_service._resource_index_repo.update_parse_submitted.assert_awaited_once_with(
        1,
        "document",
        42,
        parse_job_id="docling-job-1",
        source_parser="docling",
    )


@pytest.mark.asyncio
async def test_process_document_marks_failed_on_submit_error(processing_service):
    parser = _FakeAsyncParser()
    parser.submit = AsyncMock(side_effect=RuntimeError("submit failed"))
    processing_service._registry = _FakeRegistry(parser)
    processing_service._document_repo.update_status = AsyncMock()
    processing_service._resource_index_repo.update_parse_failed = AsyncMock()

    with pytest.raises(RuntimeError, match="submit failed"):
        await processing_service.process_document(_sample_doc())

    processing_service._document_repo.update_status.assert_awaited_with(42, DocumentStatus.FAILED)
    processing_service._resource_index_repo.update_parse_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_pending_captures_failure_and_continues(caplog):
    sessions = [object(), object()]

    @asynccontextmanager
    async def session_factory():
        yield sessions.pop(0)

    class _StubService(DocumentProcessingService):
        def __init__(self, tenant_id, db_session, file_storage):
            self.tenant_id = tenant_id
            self.db_session = db_session
            self.file_storage = file_storage

        async def _list_pending_parse_ids(self, *, limit=10):
            return [11, 12]

        async def process_document_by_id(self, document_id, *, triggered_by="worker"):
            if document_id == 11:
                raise RuntimeError("submit failed")
            return DocumentProcessOutcome.SUBMITTED

    with caplog.at_level("WARNING"):
        result = await _StubService(1, object(), object())._process_pending(
            session_factory=session_factory,
        )

    assert result == {"processed": 2, "completed": 0, "submitted": 1, "failed": 1}
    assert "document_parse_failed" in caplog.text
    assert "document_id=11" in caplog.text
    assert sessions == []


@pytest.mark.asyncio
async def test_process_document_recovers_existing_blocks_without_parser(processing_service, monkeypatch):
    parser = _FakeAsyncParser()
    submit = AsyncMock(side_effect=AssertionError("parser submit should be skipped"))
    parser.submit = submit
    processing_service._registry = _FakeRegistry(parser)
    processing_service._document_repo.update_status = AsyncMock()
    persist = AsyncMock()
    monkeypatch.setattr(processing_service, "_persist_blocks", persist)
    monkeypatch.setattr(
        "apps.shared.document.processing_service.try_read_existing_blocks",
        AsyncMock(return_value=parser.blocks),
    )

    result = await processing_service.process_document(_sample_doc())

    assert result == DocumentProcessOutcome.COMPLETED
    persist.assert_awaited_once()
    submit.assert_not_awaited()
    processing_service._document_repo.update_status.assert_awaited_with(42, DocumentStatus.ACTIVE)


@pytest.mark.asyncio
async def test_poll_one_job_recovers_when_async_parser_fails(processing_service, monkeypatch):
    parser = _FakeAsyncParser(poll_status="failed")
    processing_service._registry = _FakeRegistry(parser)
    processing_service._resource_index_repo.get_by_resource = AsyncMock(return_value=_pending_job_record())
    processing_service._document_repo.get_by_id = AsyncMock(return_value=_document_db())
    processing_service._document_repo.update_status = AsyncMock()
    processing_service._resource_index_repo.update_parse_failed = AsyncMock()
    persist = AsyncMock()
    monkeypatch.setattr(processing_service, "_persist_blocks", persist)
    monkeypatch.setattr(
        "apps.shared.document.processing_service.try_read_existing_blocks",
        AsyncMock(return_value=parser.blocks),
    )

    result = await processing_service.poll_one_job(42)

    assert result == PollJobOutcome.COMPLETED
    persist.assert_awaited_once()
    processing_service._resource_index_repo.update_parse_failed.assert_not_awaited()
    processing_service._document_repo.update_status.assert_awaited_with(42, DocumentStatus.ACTIVE)


@pytest.mark.asyncio
async def test_poll_pending_counts_completed_and_failed():
    sessions = [object(), object()]

    @asynccontextmanager
    async def session_factory():
        yield sessions.pop(0)

    class _StubService(DocumentProcessingService):
        def __init__(self, tenant_id, db_session, file_storage):
            self.tenant_id = tenant_id
            self.db_session = db_session
            self.file_storage = file_storage

        async def _list_pending_parse_job_ids(self, *, limit=10):
            return [11, 12]

        async def poll_one_job(self, resource_id):
            if resource_id == 11:
                return PollJobOutcome.FAILED
            return PollJobOutcome.COMPLETED

    result = await _StubService(1, object(), object())._poll_pending(
        session_factory=session_factory,
    )

    assert result == {"completed": 1, "failed": 1, "polled": 2}
    assert sessions == []


@pytest.mark.asyncio
async def test_run_pending_merges_process_and_poll():
    class _StubService(DocumentProcessingService):
        def __init__(self, tenant_id, db_session, file_storage):
            self.tenant_id = tenant_id
            self.db_session = db_session
            self.file_storage = file_storage

        async def _process_pending(self, *, session_factory, batch_size, triggered_by="worker"):
            return {"processed": 1, "completed": 0, "submitted": 1, "failed": 0}

        async def _poll_pending(self, *, session_factory, batch_size):
            return {"completed": 1, "failed": 0, "polled": 1}

    @asynccontextmanager
    async def session_factory():
        yield object()

    result = await _StubService(1, object(), object()).run_pending(
        session_factory=session_factory,
        batch_size=10,
    )

    assert result == {
        "queued": 1,
        "completed": 1,
        "submitted": 1,
        "failed": 0,
        "polled": 1,
    }


@pytest.mark.asyncio
async def test_list_parse_target_ids_delegates_to_repo(processing_service):
    processing_service._document_repo.list_parse_target_ids = AsyncMock(return_value=[11, 12])

    result = await processing_service.list_parse_target_ids(collection_id=9, failed_only=True)

    assert result == [11, 12]
    processing_service._document_repo.list_parse_target_ids.assert_awaited_once_with(
        1,
        document_id=None,
        collection_id=9,
        failed_only=True,
    )
