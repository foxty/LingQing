"""Tests for document sync scheduler job."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.document.sync_schemas import SyncConnectorResultResponse
from apps.shared.tasks.system.jobs.document_sync import run_document_sync_jobs


def _patch_worker(monkeypatch, *, connectors, sync_results, purged=0):
    sync_repo = AsyncMock()
    sync_repo.purge_expired_oauth_states = AsyncMock(return_value=purged)
    sync_repo.list_active_connectors = AsyncMock(return_value=connectors)

    sync_service = AsyncMock()
    sync_service.sync_connector = AsyncMock(side_effect=sync_results)

    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield session

    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_sync.DocumentSyncRepository",
        lambda _session: sync_repo,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_sync.DocumentSyncService",
        lambda tenant_id, _session, _storage: sync_service,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_sync.app_db_session",
        fake_session,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.document_sync.get_file_storage",
        lambda: object(),
    )
    return sync_repo, sync_service


@pytest.mark.asyncio
async def test_run_document_sync_jobs_success(monkeypatch):
    connector = MagicMock(id=7)
    result = SyncConnectorResultResponse(
        connector_id=7,
        added=1,
        updated=2,
        deleted=0,
        skipped=0,
    )
    _patch_worker(monkeypatch, connectors=[connector], sync_results=[result], purged=3)

    job_result = await run_document_sync_jobs(task_context={"tenant_id": 1})

    assert job_result.outcome == "success"
    assert job_result.data["details"]["connectors"] == 1
    assert job_result.data["details"]["purged_oauth_states"] == 3
    assert job_result.data["details"]["added"] == 1


@pytest.mark.asyncio
async def test_run_document_sync_jobs_skips_locked_connector(monkeypatch):
    connector = MagicMock(id=9)
    _patch_worker(monkeypatch, connectors=[connector], sync_results=[None])

    job_result = await run_document_sync_jobs(task_context={"tenant_id": 1})

    assert job_result.outcome == "success"
    assert job_result.data["details"]["connectors"] == 0
