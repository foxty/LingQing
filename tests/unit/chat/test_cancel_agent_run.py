"""Unit tests for agent run cancellation."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.tenant_app_service.chat.domain import AgentRunDomain, AgentRunStatus
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService


def _run_domain(*, status: str, thread_id: str = "thread-1", session_id: str = "sess-1") -> AgentRunDomain:
    now = datetime.now(UTC)
    return AgentRunDomain(
        id=str(uuid4()),
        tenant_id=10,
        thread_id=thread_id,
        agent_id=1,
        trigger_message_id=str(uuid4()),
        invoke_index=0,
        status=status,
        session_id=session_id,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_cancel_agent_run_from_running():
    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=10)
    run = _run_domain(status=AgentRunStatus.RUNNING)
    service.run_repo.get_run = AsyncMock(return_value=run)
    cancelled = _run_domain(status=AgentRunStatus.CANCELLED, thread_id=run.thread_id, session_id=run.session_id)
    cancelled = AgentRunDomain(
        **{**cancelled.__dict__, "id": run.id},
    )
    service.run_repo.cancel_active_run = AsyncMock(return_value=cancelled)

    hitl_repo = MagicMock()
    hitl_repo.cancel_pending_for_session = AsyncMock(return_value=0)
    with pytest.MonkeyPatch.context() as mp:
        from apps.tenant_app_service.hitl import repository as hitl_repo_mod

        mp.setattr(
            hitl_repo_mod,
            "HitlApprovalRepository",
            lambda _db: hitl_repo,
        )
        from apps.tenant_app_service.chat import agent_run_execution_registry as reg

        mp.setattr(reg, "cancel_local", lambda _run_id: False)

        result = await service.cancel_agent_run(thread_id=run.thread_id, run_id=run.id)

    assert result.status == AgentRunStatus.CANCELLED
    service.run_repo.cancel_active_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_agent_run_idempotent_when_already_cancelled():
    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=10)
    run = _run_domain(status=AgentRunStatus.CANCELLED)
    service.run_repo.get_run = AsyncMock(return_value=run)
    service.run_repo.cancel_active_run = AsyncMock()

    with pytest.MonkeyPatch.context() as mp:
        from apps.tenant_app_service.chat import agent_run_execution_registry as reg

        mp.setattr(reg, "cancel_local", lambda _run_id: False)
        result = await service.cancel_agent_run(thread_id=run.thread_id, run_id=run.id)

    assert result.status == AgentRunStatus.CANCELLED
    service.run_repo.cancel_active_run.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_agent_run_rejects_completed():
    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=10)
    run = _run_domain(status=AgentRunStatus.COMPLETED)
    service.run_repo.get_run = AsyncMock(return_value=run)

    with pytest.raises(ValidationError, match="cannot be cancelled"):
        await service.cancel_agent_run(thread_id=run.thread_id, run_id=run.id)


@pytest.mark.asyncio
async def test_cancel_agent_run_not_found():
    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=10)
    service.run_repo.get_run = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await service.cancel_agent_run(thread_id="thread-1", run_id=str(uuid4()))
