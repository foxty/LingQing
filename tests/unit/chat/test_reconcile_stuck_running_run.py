"""Reconcile closes RUNNING runs that already have a terminal AI in run messages."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.chat.domain import AgentRunDomain, AgentRunStatus
from apps.tenant_app_service.chat.domain.agent_run.policies import RUN_STALE_ACTIVE_SECONDS
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService


@pytest.mark.asyncio
async def test_thread_run_repair_finalizes_running_with_promotable_ai():
    db = AsyncMock()
    thread_runs = ThreadRunService(db, tenant_id=1)
    now = datetime.now(UTC)
    run = AgentRunDomain(
        id="run-stuck",
        tenant_id=1,
        thread_id="thread-1",
        agent_id=-1,
        trigger_message_id="human-1",
        invoke_index=0,
        status=AgentRunStatus.RUNNING,
        session_id="sess-1",
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    final_ai = MagicMock(type="ai", tool_calls=None)
    completed = AgentRunDomain(
        id=run.id,
        tenant_id=1,
        thread_id="thread-1",
        agent_id=-1,
        trigger_message_id="human-1",
        invoke_index=0,
        status=AgentRunStatus.COMPLETED,
        session_id="sess-1",
        created_at=now,
        updated_at=now,
        completed_at=now,
    )

    with (
        patch.object(thread_runs, "run_message_repo") as run_msg_repo,
        patch(
            "apps.tenant_app_service.chat.application.runs.thread_run_service.find_promotable_final_ai_row",
            return_value=final_ai,
        ),
        patch(
            "apps.tenant_app_service.chat.application.runs.thread_run_service.apply_run_closure",
            AsyncMock(),
        ) as apply_closure,
        patch.object(thread_runs, "run_repo") as run_repo,
    ):
        run_msg_repo.list_for_run = AsyncMock(return_value=[final_ai])
        run_repo.get_run = AsyncMock(return_value=completed)

        result = await thread_runs.repair_run_if_needed(run)

    assert result.status == AgentRunStatus.COMPLETED
    apply_closure.assert_awaited_once()
    assert apply_closure.await_args.kwargs["run_id"] == "run-stuck"


@pytest.mark.asyncio
async def test_thread_run_reconcile_leaves_awaiting_hitl_for_resume():
    db = AsyncMock()
    thread_runs = ThreadRunService(db, tenant_id=1)
    now = datetime.now(UTC)
    run = AgentRunDomain(
        id="run-hitl",
        tenant_id=1,
        thread_id="thread-1",
        agent_id=-1,
        trigger_message_id="human-1",
        invoke_index=0,
        status=AgentRunStatus.AWAITING_HITL,
        session_id="sess-hitl",
        created_at=now,
        updated_at=now,
        completed_at=None,
    )

    with (
        patch.object(thread_runs, "run_repo") as run_repo,
        patch.object(thread_runs, "repair_run_if_needed", AsyncMock(return_value=run)),
        patch(
            "apps.tenant_app_service.chat.application.runs.thread_run_service.apply_run_closure",
            AsyncMock(),
        ) as apply_closure,
    ):
        run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
        run_repo.get_run = AsyncMock(return_value=run)
        hitl_repo = MagicMock()
        hitl_repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        with patch(
            "apps.tenant_app_service.chat.application.runs.thread_run_service.HitlApprovalRepository",
            return_value=hitl_repo,
        ):
            await thread_runs.reconcile_before_new_turn("thread-1", -1)

    apply_closure.assert_not_called()
    run_repo.list_active_for_thread_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_thread_run_reconcile_supersedes_stale_running():
    db = AsyncMock()
    thread_runs = ThreadRunService(db, tenant_id=1)
    now = datetime.now(UTC)
    stale_started = now - timedelta(seconds=RUN_STALE_ACTIVE_SECONDS + 60)
    run = AgentRunDomain(
        id="run-stale",
        tenant_id=1,
        thread_id="thread-1",
        agent_id=-1,
        trigger_message_id="human-1",
        invoke_index=0,
        status=AgentRunStatus.RUNNING,
        session_id="sess-stale",
        created_at=stale_started,
        updated_at=stale_started,
        completed_at=None,
    )
    completed = AgentRunDomain(
        id=run.id,
        tenant_id=1,
        thread_id="thread-1",
        agent_id=-1,
        trigger_message_id="human-1",
        invoke_index=0,
        status=AgentRunStatus.COMPLETED,
        session_id="sess-stale",
        created_at=stale_started,
        updated_at=now,
        completed_at=now,
    )

    with (
        patch.object(thread_runs, "run_repo") as run_repo,
        patch.object(thread_runs, "repair_run_if_needed", AsyncMock(return_value=run)),
        patch(
            "apps.tenant_app_service.chat.application.runs.thread_run_service.apply_run_closure",
            AsyncMock(),
        ) as apply_closure,
    ):
        run_repo.list_active_for_thread_agent = AsyncMock(return_value=[run])
        run_repo.get_run = AsyncMock(return_value=completed)
        hitl_repo = MagicMock()
        hitl_repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        with patch(
            "apps.tenant_app_service.chat.application.runs.thread_run_service.HitlApprovalRepository",
            return_value=hitl_repo,
        ):
            await thread_runs.reconcile_before_new_turn("thread-1", -1)

    apply_closure.assert_awaited_once()
    assert apply_closure.await_args.kwargs["run_id"] == "run-stale"
    from apps.tenant_app_service.chat.domain.agent_run.closure import RunClosureOutcome

    assert apply_closure.await_args.kwargs["outcome"] == RunClosureOutcome.RECONCILED_BEFORE_NEW_TURN
