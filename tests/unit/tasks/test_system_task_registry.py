"""Unit tests for system task execution in ScheduledTaskExecutionService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.shared.tasks.execution_service import ScheduledTaskExecutionService
from apps.shared.tasks.system.handler_result import system_task_failed, system_task_partial, system_task_success


@pytest.mark.asyncio
async def test_execute_system_task_dispatches_by_handler_ref():
    """Test that execute_system_task resolves handler and calls it correctly."""

    # Create a mock task
    task = SimpleNamespace(
        id=1,
        tenant_id=7,
        user_id=None,
        input_params={"source": "documents", "mode": "incremental", "batch_size": 88, "unknown": 123},
        task_config={"handler_ref": "apps.shared.tasks.system.jobs.vector_sync:sync_to_vector_db"},
    )

    # Mock the imported handler function
    async def _fake_handler(*, task_context, source="all", mode="incremental", batch_size=100):
        return system_task_success(source=source, mode=mode, batch_size=batch_size)

    service = ScheduledTaskExecutionService()

    # Patch importlib.import_module to return our mock module
    with patch("importlib.import_module") as mock_import:
        mock_module = AsyncMock()
        mock_module.sync_to_vector_db = _fake_handler
        mock_import.return_value = mock_module

        result = await service.execute_system_task(task)

    assert result.success is True
    assert result.payload["outcome"] == "success"
    assert result.payload["source"] == "documents"
    assert result.payload["mode"] == "incremental"
    assert result.payload["batch_size"] == 88


@pytest.mark.asyncio
async def test_execute_system_task_raises_for_unknown_handler_ref():
    """Test that unknown handler_ref raises ValueError."""
    task = SimpleNamespace(task_config={"handler_ref": "apps.shared.tasks.system.jobs.unknown:missing"})

    service = ScheduledTaskExecutionService()

    with pytest.raises(ValueError, match="Unknown system handler_ref"):
        await service.execute_system_task(task)


@pytest.mark.asyncio
async def test_execute_system_task_injects_task_context_into_var_kwargs():
    """Test that task_context is injected into handler kwargs."""

    task = SimpleNamespace(
        id=2,
        tenant_id=9,
        user_id=None,
        task_config={"handler_ref": "apps.shared.tasks.system.jobs.vector_sync:sync_to_vector_db"},
        input_params={"source": "assets"},
    )

    async def _fake_handler(**kwargs):
        return system_task_success(**kwargs)

    service = ScheduledTaskExecutionService()

    with patch("importlib.import_module") as mock_import:
        mock_module = AsyncMock()
        mock_module.sync_to_vector_db = _fake_handler
        mock_import.return_value = mock_module

        result = await service.execute_system_task(task)

    assert result.success is True
    assert result.payload["outcome"] == "success"
    assert result.payload["task_context"]["tenant_id"] == 9
    assert result.payload["source"] == "assets"


@pytest.mark.asyncio
async def test_execute_system_task_treats_partial_as_completed():
    task = SimpleNamespace(
        id=3,
        tenant_id=2,
        user_id=None,
        input_params={},
        task_config={"handler_ref": "apps.shared.tasks.system.jobs.document_parse:run_document_parse_jobs"},
    )

    async def _fake_handler(*, task_context, batch_size=None):
        return system_task_partial("1 job failed", completed=1, failed=1)

    service = ScheduledTaskExecutionService()
    with patch("importlib.import_module") as mock_import:
        mock_module = AsyncMock()
        mock_module.run_document_parse_jobs = _fake_handler
        mock_import.return_value = mock_module
        result = await service.execute_system_task(task)

    assert result.success is True
    assert result.payload["outcome"] == "partial"
    assert result.error_message == "1 job failed"


@pytest.mark.asyncio
async def test_execute_system_task_treats_failed_as_unsuccessful():
    task = SimpleNamespace(
        id=4,
        tenant_id=2,
        user_id=None,
        input_params={},
        task_config={"handler_ref": "apps.shared.tasks.system.jobs.document_parse:run_document_parse_jobs"},
    )

    async def _fake_handler(*, task_context, batch_size=None):
        return system_task_failed("2 jobs failed")

    service = ScheduledTaskExecutionService()
    with patch("importlib.import_module") as mock_import:
        mock_module = AsyncMock()
        mock_module.run_document_parse_jobs = _fake_handler
        mock_import.return_value = mock_module
        result = await service.execute_system_task(task)

    assert result.success is False
    assert result.payload["outcome"] == "failed"
