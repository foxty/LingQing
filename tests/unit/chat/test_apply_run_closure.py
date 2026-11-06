"""Tests for unified run closure dispatcher."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.agents.langgraph_invoke import AgentInvokeOutcome
from apps.tenant_app_service.chat.application.runs.closure import apply_run_closure
from apps.tenant_app_service.chat.application.runs.closure import RunClosureRollup
from apps.tenant_app_service.chat.application.runs.invoke_closure import closure_outcome_from_invoke
from apps.tenant_app_service.chat.domain.agent_run.closure import RunClosureOutcome


def test_closure_outcome_from_invoke_maps_hitl_interrupt():
    assert closure_outcome_from_invoke(AgentInvokeOutcome.INTERRUPTED_FOR_HITL) == RunClosureOutcome.PAUSED_FOR_HITL


def _mock_executor(*, db=None, tenant_id=1):
    executor = MagicMock()
    executor.db = db or AsyncMock()
    executor.tenant_id = tenant_id
    executor.finalize_run_for_main = AsyncMock()
    executor.mark_run_failed = AsyncMock()
    executor.mark_run_completed = AsyncMock()
    return executor


@pytest.mark.asyncio
async def test_apply_run_closure_completed_finalizes_run():
    executor = _mock_executor()

    await apply_run_closure(
        executor,
        run_id="run-1",
        outcome=RunClosureOutcome.COMPLETED,
    )

    executor.finalize_run_for_main.assert_awaited_once_with("run-1")


@pytest.mark.asyncio
async def test_apply_run_closure_cancelled_skips_promotion():
    executor = _mock_executor()

    await apply_run_closure(executor, run_id="run-1", outcome=RunClosureOutcome.CANCELLED)

    executor.finalize_run_for_main.assert_not_called()
    executor.mark_run_failed.assert_not_called()


@pytest.mark.asyncio
async def test_apply_run_closure_schedules_rollup():
    executor = _mock_executor()

    with patch(
        "apps.tenant_app_service.chat.application.runs.closure.schedule_run_closure_rollup",
    ) as schedule:
        await apply_run_closure(
            executor,
            run_id=None,
            outcome=RunClosureOutcome.COMPLETED,
            rollup=RunClosureRollup(session_id="sess", thread_id="thread", run_id="run-1"),
        )

    schedule.assert_called_once()


@pytest.mark.asyncio
async def test_apply_run_closure_failed_marks_run_failed():
    executor = _mock_executor()

    await apply_run_closure(executor, run_id="run-1", outcome=RunClosureOutcome.FAILED)

    executor.mark_run_failed.assert_awaited_once_with("run-1")


@pytest.mark.asyncio
async def test_apply_run_closure_paused_for_hitl_does_not_touch_run():
    executor = _mock_executor()

    await apply_run_closure(executor, run_id="run-1", outcome=RunClosureOutcome.PAUSED_FOR_HITL)

    executor.finalize_run_for_main.assert_not_called()
    executor.mark_run_failed.assert_not_called()


@pytest.mark.asyncio
async def test_apply_run_closure_reconciled_before_new_turn_marks_completed_without_promotion():
    executor = _mock_executor()

    await apply_run_closure(executor, run_id="run-1", outcome=RunClosureOutcome.RECONCILED_BEFORE_NEW_TURN)

    executor.mark_run_completed.assert_awaited_once_with("run-1")
    executor.finalize_run_for_main.assert_not_called()


@pytest.mark.asyncio
async def test_on_invoke_outcome_delegates_to_apply_run_closure():
    from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService

    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=1)

    with patch(
        "apps.tenant_app_service.chat.application.runs.thread_run_service.apply_run_closure",
        AsyncMock(),
    ) as apply_closure:
        await service.on_invoke_outcome("run-1", AgentInvokeOutcome.COMPLETED)

    apply_closure.assert_awaited_once()
    assert apply_closure.await_args.kwargs["outcome"] == RunClosureOutcome.COMPLETED
