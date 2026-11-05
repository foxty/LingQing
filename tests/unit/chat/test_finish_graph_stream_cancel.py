"""Stream teardown maps user cancel to CANCELLED invoke outcome, not FAILED."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from apps.tenant_app_service.agents.langgraph_invoke import AgentInvokeOutcome
from apps.tenant_app_service.chat.domain import AgentRunStatus
from apps.tenant_app_service.chat.turn_service import ChatTurnService

from tests.unit.chat.test_cancel_agent_run import _run_domain


@pytest.mark.asyncio
async def test_finish_graph_stream_failed_but_db_cancelled_uses_cancelled_outcome():
    db = AsyncMock()
    service = ChatTurnService(tenant_id=1, db=db)
    cancelled_run = _run_domain(status=AgentRunStatus.CANCELLED)
    run_id = cancelled_run.id

    with patch("apps.tenant_app_service.chat.application.turn.turn_helpers.ThreadRunService") as trs_cls:
        thread_runs = AsyncMock()
        thread_runs.get_run = AsyncMock(return_value=cancelled_run)
        trs_cls.return_value = thread_runs

        await service._finish_graph_stream(MagicMock(), {}, run_id, failed=True)

    thread_runs.on_invoke_outcome.assert_awaited_once_with(
        run_id, AgentInvokeOutcome.CANCELLED, rollup=None
    )


@pytest.mark.asyncio
async def test_finish_graph_stream_cancelled_flag():
    db = AsyncMock()
    service = ChatTurnService(tenant_id=1, db=db)
    run_id = str(uuid4())

    with patch("apps.tenant_app_service.chat.application.turn.turn_helpers.ThreadRunService") as trs_cls:
        thread_runs = AsyncMock()
        trs_cls.return_value = thread_runs

        await service._finish_graph_stream(MagicMock(), {}, run_id, cancelled=True)

    thread_runs.on_invoke_outcome.assert_awaited_once_with(
        run_id, AgentInvokeOutcome.CANCELLED, rollup=None
    )
