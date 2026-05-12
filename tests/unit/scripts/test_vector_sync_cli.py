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
from scripts.vector_sync_cli import _result_payload, _result_succeeded, handle_sync


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
