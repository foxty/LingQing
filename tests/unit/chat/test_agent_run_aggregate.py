"""Unit tests for AgentRun aggregate rules (no DB)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.chat.domain import AgentRun
from apps.tenant_app_service.chat.domain import AgentRunDomain, AgentRunStatus


def _run(*, status: str = AgentRunStatus.RUNNING) -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun.from_domain(
        AgentRunDomain(
            id=str(uuid4()),
            tenant_id=1,
            thread_id="thread-a",
            agent_id=-1,
            trigger_message_id="human-1",
            invoke_index=0,
            status=status,
            session_id=str(uuid4()),
            created_at=now,
            updated_at=now,
        )
    )


def test_ensure_belongs_to_thread():
    run = _run()
    run.ensure_belongs_to_thread("thread-a")
    with pytest.raises(ValidationError) as exc:
        run.ensure_belongs_to_thread("other")
    assert exc.value.details.get("code") == "RUN_THREAD_MISMATCH"


def test_cancel_idempotent_when_already_cancelled():
    run = _run(status=AgentRunStatus.CANCELLED)
    run.ensure_cancellable()


def test_cancel_rejects_completed():
    run = _run(status=AgentRunStatus.COMPLETED)
    with pytest.raises(ValidationError) as exc:
        run.ensure_cancellable()
    assert exc.value.details.get("code") == "RUN_NOT_CANCELLABLE"


def test_already_finished_error_code():
    run = _run(status=AgentRunStatus.COMPLETED)
    err = run.already_finished_cancel_error()
    assert err.details.get("code") == "RUN_ALREADY_FINISHED"


def test_finalize_skips_hitl_failed_cancelled():
    for status in (
        AgentRunStatus.AWAITING_HITL,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    ):
        assert _run(status=status).skips_finalize_promotion()

    assert not _run(status=AgentRunStatus.RUNNING).skips_finalize_promotion()


def test_finalize_marks_completed_only_when_running():
    assert _run(status=AgentRunStatus.RUNNING).should_mark_completed_after_finalize()
    assert not _run(status=AgentRunStatus.COMPLETED).should_mark_completed_after_finalize()


def test_transition_to_running_from_queued():
    run = _run(status=AgentRunStatus.QUEUED)
    update = run.transition_to_running()
    assert update is not None
    assert update.status == AgentRunStatus.RUNNING
    assert update.completed_at is None


def test_transition_to_running_idempotent():
    assert _run(status=AgentRunStatus.RUNNING).transition_to_running() is None


def test_transition_to_failed_skips_cancelled():
    now = datetime.now(UTC)
    assert _run(status=AgentRunStatus.CANCELLED).transition_to_failed(now) is None


def test_transition_resume_from_hitl():
    transition = _run(status=AgentRunStatus.AWAITING_HITL).transition_resume_from_hitl()
    assert transition is not None
    assert transition.expected == AgentRunStatus.AWAITING_HITL
    assert transition.new == AgentRunStatus.RUNNING


def test_transition_reconcile_close_for_awaiting_hitl():
    now = datetime.now(UTC)
    update = _run(status=AgentRunStatus.AWAITING_HITL).transition_reconcile_close(now)
    assert update is not None
    assert update.status == AgentRunStatus.COMPLETED
    assert update.completed_at == now
