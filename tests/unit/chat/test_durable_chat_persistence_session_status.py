"""Session status tests (agent runs + main timeline; no chat_messages)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.session_status_service import resolve_session_status

_HITL = "apps.tenant_app_service.chat.session_status_service.HitlApprovalRepository"
_MAIN = "apps.tenant_app_service.chat.session_status_service.MainMessageRepository"
_RUN = "apps.tenant_app_service.chat.session_status_service.AgentRunRepository"
_RUN_MSG = "apps.tenant_app_service.chat.session_status_service.AgentRunMessageRepository"


def _run_repo_mocks(*, active=None, latest=None):
    run_repo = AsyncMock()
    run_repo.list_active_for_thread_agent = AsyncMock(return_value=list(active or []))
    run_repo.get_latest_for_thread_agent = AsyncMock(return_value=latest)
    return run_repo


def _msg_repo_mocks(*, promoted=False, run_ai=False):
    main_repo = AsyncMock()
    main_repo.has_promoted_ai_for_session = AsyncMock(return_value=promoted)
    run_msg_repo = AsyncMock()
    run_msg_repo.has_ai_for_session = AsyncMock(return_value=run_ai)
    return main_repo, run_msg_repo


@pytest.mark.asyncio
async def test_pending_hitl():
    pending = SimpleNamespace(proposal_id="hitl_1", tool_name="bash", session_id="session-hitl")
    main_repo, run_msg_repo = _msg_repo_mocks(promoted=True)

    with (
        patch(_HITL) as hitl_cls,
        patch(_MAIN, return_value=main_repo),
        patch(_RUN, return_value=_run_repo_mocks()),
        patch(_RUN_MSG, return_value=run_msg_repo),
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=pending)
        hitl_cls.return_value.get_latest_approved_by_thread = AsyncMock(return_value=None)

        status = await resolve_session_status(tenant_id=1, db=AsyncMock(), thread_id="t1", agent_id=-1)

    assert status.status == "awaiting_hitl"
    assert status.pending_hitl.proposal_id == "hitl_1"


@pytest.mark.asyncio
async def test_awaiting_hitl_when_active_run_has_interim_ai_only():
    run = SimpleNamespace(
        session_id="session-hitl-pause",
        status="awaiting_hitl",
        created_at=datetime.now(UTC),
    )
    main_repo, run_msg_repo = _msg_repo_mocks(promoted=False, run_ai=True)

    with (
        patch(_HITL) as hitl_cls,
        patch(_MAIN, return_value=main_repo),
        patch(_RUN, return_value=_run_repo_mocks(active=[run])),
        patch(_RUN_MSG, return_value=run_msg_repo),
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        hitl_cls.return_value.get_latest_approved_by_thread = AsyncMock(return_value=None)

        status = await resolve_session_status(tenant_id=1, db=AsyncMock(), thread_id="t1", agent_id=-1)

    assert status.status == "awaiting_hitl"
    assert status.session_id == "session-hitl-pause"
    assert status.has_ai_response is True


@pytest.mark.asyncio
async def test_running_when_active_run_without_ai():
    run = SimpleNamespace(
        session_id="session-running",
        status="running",
        created_at=datetime.now(UTC),
    )
    main_repo, run_msg_repo = _msg_repo_mocks()

    with (
        patch(_HITL) as hitl_cls,
        patch(_MAIN, return_value=main_repo),
        patch(_RUN, return_value=_run_repo_mocks(active=[run])),
        patch(_RUN_MSG, return_value=run_msg_repo),
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        hitl_cls.return_value.get_latest_approved_by_thread = AsyncMock(return_value=None)

        status = await resolve_session_status(tenant_id=1, db=AsyncMock(), thread_id="t1", agent_id=-1)

    assert status.status == "running"
    assert status.session_id == "session-running"
    assert status.has_ai_response is False


@pytest.mark.asyncio
async def test_completed_when_stale_run_without_ai():
    latest = SimpleNamespace(
        session_id="session-stale",
        status="running",
        created_at=datetime.now(UTC) - timedelta(minutes=20),
    )
    main_repo, run_msg_repo = _msg_repo_mocks()

    with (
        patch(_HITL) as hitl_cls,
        patch(_MAIN, return_value=main_repo),
        patch(_RUN, return_value=_run_repo_mocks(latest=latest)),
        patch(_RUN_MSG, return_value=run_msg_repo),
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        hitl_cls.return_value.get_latest_approved_by_thread = AsyncMock(return_value=None)

        status = await resolve_session_status(tenant_id=1, db=AsyncMock(), thread_id="t1", agent_id=-1)

    assert status.status == "completed"
    assert status.has_ai_response is False


@pytest.mark.asyncio
async def test_hitl_approved_pending_continue():
    approved = SimpleNamespace(
        proposal_id="hitl_approved",
        tool_name="bash",
        session_id="session-old",
        approved_at=datetime.now(UTC),
    )
    main_repo, run_msg_repo = _msg_repo_mocks(promoted=True)

    with (
        patch(_HITL) as hitl_cls,
        patch(_MAIN, return_value=main_repo),
        patch(_RUN, return_value=_run_repo_mocks(latest=None)),
        patch(_RUN_MSG, return_value=run_msg_repo),
    ):
        hitl_cls.return_value.get_latest_pending_by_thread = AsyncMock(return_value=None)
        hitl_cls.return_value.get_latest_approved_by_thread = AsyncMock(return_value=approved)

        status = await resolve_session_status(tenant_id=1, db=AsyncMock(), thread_id="t1", agent_id=-1)

    assert status.status == "hitl_approved_pending_continue"
