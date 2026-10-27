"""Active run snapshot on ThreadRunService (poll + admission)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService

_RUN = "apps.tenant_app_service.chat.thread_run_service.AgentRunRepository"
_HITL = "apps.tenant_app_service.chat.thread_run_service.HitlApprovalRepository"


def _run_domain(*, status: str, session_id: str = "session-1") -> SimpleNamespace:
    return SimpleNamespace(
        id="run-1",
        session_id=session_id,
        status=status,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_idle_when_no_active_run():
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    with (
        patch(_RUN, return_value=run_repo),
        patch(_HITL) as hitl_cls,
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        snapshot = await ThreadRunService(AsyncMock(), 1).get_active_run(
            thread_id="t1",
            agent_id=-1,
            repair=False,
        )

    assert snapshot.run_id is None
    assert snapshot.run_status is None


@pytest.mark.asyncio
async def test_running_run_exposed_with_session_id():
    run = _run_domain(status=AgentRunStatus.RUNNING, session_id="session-running")
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[run])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    with (
        patch(_RUN, return_value=run_repo),
        patch(_HITL) as hitl_cls,
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        snapshot = await ThreadRunService(AsyncMock(), 1).get_active_run(
            thread_id="t1",
            agent_id=-1,
            repair=False,
        )

    assert snapshot.run_id == "run-1"
    assert snapshot.run_status == AgentRunStatus.RUNNING
    assert snapshot.session_id == "session-running"


@pytest.mark.asyncio
async def test_pending_hitl_without_active_run():
    pending = SimpleNamespace(proposal_id="hitl_1", tool_name="bash", session_id="session-hitl")
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    with (
        patch(_RUN, return_value=run_repo),
        patch(_HITL) as hitl_cls,
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=pending)
        snapshot = await ThreadRunService(AsyncMock(), 1).get_active_run(
            thread_id="t1",
            agent_id=-1,
            repair=False,
        )

    assert snapshot.run_id is None
    assert snapshot.pending_hitl is not None
    assert snapshot.pending_hitl.proposal_id == "hitl_1"


@pytest.mark.asyncio
async def test_repair_clears_terminal_run():
    run = _run_domain(status=AgentRunStatus.RUNNING)
    repaired = _run_domain(status=AgentRunStatus.COMPLETED)
    service = ThreadRunService(AsyncMock(), 1)
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[run])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    with (
        patch.object(service, "repair_run_if_needed", AsyncMock(return_value=repaired)) as repair,
        patch(_HITL) as hitl_cls,
        patch.object(service, "run_repo", run_repo),
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        snapshot = await service.get_active_run(thread_id="t1", agent_id=-1, repair=True)

    assert snapshot.run_id is None
    repair.assert_awaited_once()
