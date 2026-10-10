"""Unit tests for vector_sync_cli handler result handling."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from apps.shared.tasks.system.handler_result import (
    system_task_failed,
    system_task_partial,
    system_task_success,
)
from scripts.vector_sync_cli import (
    _is_chroma_collection_missing_error,
    _result_payload,
    _result_succeeded,
    handle_reset_collection,
    handle_sync,
)


def test_result_payload_from_system_task_handler_result():
    result = system_task_success(status="completed", total_synced=3, total_failed=0)
    payload = _result_payload(result)
    assert payload["outcome"] == "success"
    assert payload["total_synced"] == 3
    assert payload["total_failed"] == 0


def test_result_payload_from_dict_passthrough():
    payload = _result_payload({"total_synced": 1, "status": "completed"})
    assert payload["total_synced"] == 1


def test_result_succeeded_for_success_and_partial():
    assert _result_succeeded(system_task_success()) is True
    assert _result_succeeded(system_task_partial("warn", total_synced=1, total_failed=1)) is True
    assert _result_succeeded(system_task_failed("boom")) is False


def test_result_succeeded_for_legacy_dict_status():
    assert _result_succeeded({"status": "completed"}) is True


@pytest.mark.asyncio
async def test_handle_sync_aggregates_system_task_handler_result():
    args = SimpleNamespace(source="all", mode="incremental", tenant_id=2)

    async def _fake_sync(**kwargs):
        return system_task_success(status="completed", total_synced=5, total_failed=1)

    with (
        patch("scripts.vector_sync_cli._resolve_target_tenant_ids", AsyncMock(return_value=[2])),
        patch("scripts.vector_sync_cli.sync_to_vector_db", AsyncMock(side_effect=_fake_sync)),
    ):
        exit_code = await handle_sync(args)

    assert exit_code == 0


def test_is_chroma_collection_missing_error():
    assert _is_chroma_collection_missing_error(Exception("Collection tenant_1 does not exist")) is True
    assert _is_chroma_collection_missing_error(Exception("Not Found")) is True
    assert _is_chroma_collection_missing_error(Exception("dimension mismatch")) is False


@pytest.mark.asyncio
async def test_handle_reset_collection_requires_tenant_id():
    args = SimpleNamespace(tenant_id=None, dry_run=False, mark_stale=True)
    assert await handle_reset_collection(args) == 1


@pytest.mark.asyncio
async def test_handle_reset_collection_dry_run():
    args = SimpleNamespace(tenant_id=7, dry_run=True, mark_stale=True)
    with patch(
        "scripts.vector_sync_cli._load_chroma_tenant_stats",
        AsyncMock(return_value=({7: {"chroma_collection_exists": True, "chroma_vector_count": 42}}, None)),
    ):
        assert await handle_reset_collection(args) == 0


@pytest.mark.asyncio
async def test_handle_reset_collection_deletes_and_marks_stale():
    args = SimpleNamespace(tenant_id=3, dry_run=False, mark_stale=True)
    mock_index_service = SimpleNamespace(
        rag_manager=SimpleNamespace(clear_collection=AsyncMock()),
        mark_all_vectors_stale=AsyncMock(return_value=11),
    )

    with (
        patch("scripts.vector_sync_cli.asyncio.sleep", AsyncMock()),
        patch(
            "scripts.vector_sync_cli._load_chroma_tenant_stats",
            AsyncMock(return_value=({3: {"chroma_collection_exists": True, "chroma_vector_count": 5}}, None)),
        ),
        patch("scripts.vector_sync_cli.get_file_storage", return_value=None),
        patch(
            "scripts.vector_sync_cli.ResourceIndexService.create",
            AsyncMock(return_value=mock_index_service),
        ),
        patch("scripts.vector_sync_cli.app_db_session") as mock_session_ctx,
    ):
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        exit_code = await handle_reset_collection(args)

    assert exit_code == 0
    mock_index_service.rag_manager.clear_collection.assert_awaited_once()
    mock_index_service.mark_all_vectors_stale.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
