"""Executing run snapshots on ThreadRunService (poll + admission)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.domain import AgentRunStatus
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService

_HITL = "apps.tenant_app_service.chat.application.runs.thread_run_service.HitlApprovalRepository"


def _run_domain(*, status: str, session_id: str = "session-1", run_id: str = "run-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        session_id=session_id,
        status=status,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_get_active_runs_empty_when_idle():
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    runs = await ThreadRunService(AsyncMock(), 1, run_repo=run_repo).get_active_runs(
        thread_id="t1",
        agent_id=-1,
        repair=False,
    )
    assert runs == []


@pytest.mark.asyncio
async def test_get_active_runs_excludes_awaiting_hitl_from_repo():
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
    run_repo.get_latest_for_thread_agent = AsyncMock(
        return_value=_run_domain(status=AgentRunStatus.AWAITING_HITL),
    )

    runs = await ThreadRunService(AsyncMock(), 1, run_repo=run_repo).get_active_runs(
        thread_id="t1",
        agent_id=-1,
        repair=False,
    )
    assert runs == []


@pytest.mark.asyncio
async def test_any_active_runs_false_when_only_hitl_paused():
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
    run_repo.get_latest_for_thread_agent = AsyncMock(
        return_value=_run_domain(status=AgentRunStatus.AWAITING_HITL),
    )

    assert not await ThreadRunService(AsyncMock(), 1, run_repo=run_repo).any_active_runs(
        thread_id="t1",
        agent_id=-1,
        repair=False,
    )


@pytest.mark.asyncio
async def test_running_run_in_get_active_runs_and_snapshot():
    run = _run_domain(status=AgentRunStatus.RUNNING, session_id="session-running")
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[run])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    with patch(_HITL) as hitl_cls:
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        service = ThreadRunService(AsyncMock(), 1, run_repo=run_repo)
        runs = await service.get_active_runs(thread_id="t1", agent_id=-1, repair=False)
        snapshot = await service.get_active_run(thread_id="t1", agent_id=-1, repair=False)

    assert len(runs) == 1
    assert await service.any_active_runs(thread_id="t1", agent_id=-1, repair=False)
    assert snapshot.run_id == "run-1"
    assert snapshot.run_status == AgentRunStatus.RUNNING
    assert snapshot.session_id == "session-running"


@pytest.mark.asyncio
async def test_pending_hitl_without_executing_run():
    pending = SimpleNamespace(proposal_id="hitl_1", tool_name="bash", session_id="session-hitl")
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    with patch(_HITL) as hitl_cls:
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=pending)
        snapshot = await ThreadRunService(AsyncMock(), 1, run_repo=run_repo).get_active_run(
            thread_id="t1",
            agent_id=-1,
            repair=False,
        )

    assert snapshot.run_id is None
    assert snapshot.pending_hitl is not None
    assert snapshot.pending_hitl.proposal_id == "hitl_1"


@pytest.mark.asyncio
async def test_repair_clears_terminal_run_from_active_list():
    run = _run_domain(status=AgentRunStatus.RUNNING)
    repaired = _run_domain(status=AgentRunStatus.COMPLETED)
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[run])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)
    service = ThreadRunService(AsyncMock(), 1, run_repo=run_repo)

    with (
        patch.object(service, "repair_run_if_needed", AsyncMock(return_value=repaired)) as repair,
        patch(_HITL) as hitl_cls,
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        runs = await service.get_active_runs(thread_id="t1", agent_id=-1, repair=True)
        snapshot = await service.get_active_run(thread_id="t1", agent_id=-1, repair=True)

    assert runs == []
    assert snapshot.run_id is None
    assert repair.await_count >= 1


@pytest.mark.asyncio
async def test_get_active_runs_returns_all_executing_newest_first():
    first = _run_domain(status=AgentRunStatus.RUNNING, session_id="session-first", run_id="run-first")
    second = _run_domain(status=AgentRunStatus.QUEUED, session_id="session-second", run_id="run-second")
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=[first, second])
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=None)

    runs = await ThreadRunService(AsyncMock(), 1, run_repo=run_repo).get_active_runs(
        thread_id="t1",
        agent_id=-1,
        repair=False,
    )

    assert [r.id for r in runs] == ["run-first", "run-second"]
    assert await ThreadRunService(AsyncMock(), 1, run_repo=run_repo).any_active_runs(
        thread_id="t1",
        agent_id=-1,
        repair=False,
    )
