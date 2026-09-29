"""Tests for document parse scheduler job."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from apps.shared.tasks.system.jobs.document_parse import run_document_parse_jobs


def _patch_worker(monkeypatch, result):
    processing = AsyncMock()
    processing.run_pending = AsyncMock(return_value=result)

    @asynccontextmanager
    async def fake_session():
        yield object()

    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_parse.DocumentParsePipeline",
        lambda tenant_id, session, file_storage: processing,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_parse.app_db_session",
        fake_session,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_parse.get_file_storage",
        lambda: object(),
    )
    return processing


@pytest.mark.asyncio
async def test_run_document_parse_jobs_success(monkeypatch):
    _patch_worker(
        monkeypatch,
        {"queued": 1, "completed": 1, "submitted": 0, "failed": 0, "polled": 0},
    )
    result = await run_document_parse_jobs(task_context={"tenant_id": 1})
    assert result.outcome == "success"


@pytest.mark.asyncio
async def test_run_document_parse_jobs_aggregates_async_submit_and_poll(monkeypatch):
    _patch_worker(
        monkeypatch,
        {"queued": 1, "completed": 1, "submitted": 1, "failed": 0, "polled": 1},
    )
    result = await run_document_parse_jobs(task_context={"tenant_id": 1})
    assert result.outcome == "success"
    details = result.data["details"]
    assert details["queued"] == 1
    assert details["submitted"] == 1
    assert details["completed"] == 1
    assert details["polled"] == 1


@pytest.mark.asyncio
async def test_run_document_parse_jobs_all_failed(monkeypatch):
    _patch_worker(
        monkeypatch,
        {"queued": 0, "completed": 0, "submitted": 0, "failed": 2, "polled": 2},
    )
    result = await run_document_parse_jobs(task_context={"tenant_id": 1})
    assert result.outcome == "failed"
    assert result.error_message == "Document parse worker failed for 2 job(s)"
    assert result.data["details"]["failed"] == 2
    assert result.data["details"]["polled"] == 2


@pytest.mark.asyncio
async def test_run_document_parse_jobs_partial(monkeypatch):
    _patch_worker(
        monkeypatch,
        {"queued": 2, "completed": 1, "submitted": 0, "failed": 1, "polled": 0},
    )
    result = await run_document_parse_jobs(task_context={"tenant_id": 1})
    assert result.outcome == "partial"
    assert result.error_message == "Document parse worker failed for 1 job(s)"
    assert result.data["details"]["completed"] == 1
    assert result.data["details"]["failed"] == 1
