"""Reconcile closes RUNNING runs that already have a terminal AI in run messages."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain, AgentRunStatus
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.turn_service import ChatTurnService


@pytest.mark.asyncio
async def test_reconcile_delegates_to_thread_run_service():
    db = AsyncMock()
    service = ChatTurnService(tenant_id=1, db=db)

    with patch.object(ThreadRunService, "reconcile_before_new_turn", AsyncMock()) as reconcile:
        await service._reconcile_active_runs_before_new_turn("thread-1", -1)

    reconcile.assert_awaited_once_with("thread-1", -1)


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
            "apps.tenant_app_service.chat.thread_run_service.find_promotable_final_ai_row",
            return_value=final_ai,
        ),
        patch.object(thread_runs, "finalize_run_for_main", AsyncMock()) as finalize,
        patch.object(thread_runs, "run_repo") as run_repo,
    ):
        run_msg_repo.list_for_run = AsyncMock(return_value=[final_ai])
        run_repo.get_run = AsyncMock(return_value=completed)

        result = await thread_runs.repair_run_if_needed(run)

    assert result.status == AgentRunStatus.COMPLETED
    finalize.assert_awaited_once_with("run-stuck")
