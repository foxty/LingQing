"""Agent run aggregate root — lifecycle invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.chat.domain.agent_run.policies import is_stale_active_run
from apps.tenant_app_service.chat.domain.agent_run.state import AgentRunState
from apps.tenant_app_service.chat.domain.agent_run.status import (
    ACTIVE_AGENT_RUN_STATUSES,
    TERMINAL_AGENT_RUN_STATUSES,
    AgentRunStatus,
)
from apps.tenant_app_service.chat.domain.agent_run.transitions import (
    AtomicStatusTransition,
    RunStatusUpdate,
)


@dataclass(frozen=True)
class AgentRun:
    """Consistency boundary for one agent invocation on a thread."""

    _state: AgentRunState

    @classmethod
    def from_state(cls, state: AgentRunState) -> AgentRun:
        return cls(_state=state)

    from_domain = from_state  # backward-compatible alias

    def to_state(self) -> AgentRunState:
        return self._state

    to_domain = to_state  # backward-compatible alias

    @property
    def id(self) -> str:
        return self._state.id

    @property
    def tenant_id(self) -> int:
        return self._state.tenant_id

    @property
    def thread_id(self) -> str:
        return self._state.thread_id

    @property
    def agent_id(self) -> int:
        return self._state.agent_id

    @property
    def trigger_message_id(self) -> str:
        return self._state.trigger_message_id

    @property
    def invoke_index(self) -> int:
        return self._state.invoke_index

    @property
    def status(self) -> str:
        return self._state.status

    @property
    def session_id(self) -> str:
        return self._state.session_id

    @property
    def created_at(self) -> datetime:
        return self._state.created_at

    @property
    def updated_at(self) -> datetime:
        return self._state.updated_at

    @property
    def completed_at(self) -> datetime | None:
        return self._state.completed_at

    @property
    def is_cancelled(self) -> bool:
        return self.status == AgentRunStatus.CANCELLED

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_AGENT_RUN_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_AGENT_RUN_STATUSES

    @property
    def is_terminal_finished(self) -> bool:
        return self.status in (AgentRunStatus.COMPLETED, AgentRunStatus.FAILED)

    def ensure_belongs_to_thread(self, thread_id: str) -> None:
        if self.thread_id != thread_id:
            raise ValidationError(
                "Agent run does not belong to this thread",
                details={"code": "RUN_THREAD_MISMATCH", "run_id": self.id, "thread_id": thread_id},
            )

    def ensure_cancellable(self) -> None:
        if self.is_cancelled:
            return
        if self.status in (
            AgentRunStatus.QUEUED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.AWAITING_HITL,
        ):
            return
        raise ValidationError(
            f"Agent run cannot be cancelled from status {self.status}",
            details={"code": "RUN_NOT_CANCELLABLE", "run_id": self.id, "status": self.status},
        )

    def already_finished_cancel_error(self) -> ValidationError:
        return ValidationError(
            "Agent run already finished",
            details={
                "code": "RUN_ALREADY_FINISHED",
                "run_id": self.id,
                "status": self.status,
            },
        )

    def skips_finalize_promotion(self) -> bool:
        """Do not promote AI or auto-complete while paused or terminal."""
        return self.status in (
            AgentRunStatus.AWAITING_HITL,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        )

    def should_mark_completed_after_finalize(self) -> bool:
        return self.status == AgentRunStatus.RUNNING

    def _completed_update(self, now: datetime) -> RunStatusUpdate:
        return RunStatusUpdate(status=AgentRunStatus.COMPLETED, completed_at=now)

    def _failed_update(self, now: datetime) -> RunStatusUpdate:
        return RunStatusUpdate(status=AgentRunStatus.FAILED, completed_at=now)

    def transition_to_running(self) -> RunStatusUpdate | None:
        """Start or continue execution (``queued`` → ``running``)."""
        if self.status == AgentRunStatus.RUNNING:
            return None
        if self.status == AgentRunStatus.QUEUED:
            return RunStatusUpdate(status=AgentRunStatus.RUNNING)
        raise ValidationError(
            f"Agent run cannot start from status {self.status}",
            details={"code": "RUN_INVALID_TRANSITION", "run_id": self.id, "status": self.status},
        )

    def transition_to_awaiting_hitl(self) -> RunStatusUpdate | None:
        if self.status == AgentRunStatus.AWAITING_HITL:
            return None
        if self.status == AgentRunStatus.RUNNING:
            return RunStatusUpdate(status=AgentRunStatus.AWAITING_HITL)
        raise ValidationError(
            f"Agent run cannot pause for HITL from status {self.status}",
            details={"code": "RUN_INVALID_TRANSITION", "run_id": self.id, "status": self.status},
        )

    def transition_to_completed(self, now: datetime) -> RunStatusUpdate | None:
        if self.status == AgentRunStatus.COMPLETED:
            return None
        if self.status == AgentRunStatus.RUNNING:
            return self._completed_update(now)
        raise ValidationError(
            f"Agent run cannot complete from status {self.status}",
            details={"code": "RUN_INVALID_TRANSITION", "run_id": self.id, "status": self.status},
        )

    def transition_to_failed(self, now: datetime) -> RunStatusUpdate | None:
        if self.is_cancelled or self.is_terminal:
            return None
        if self.status in (
            AgentRunStatus.QUEUED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.AWAITING_HITL,
        ):
            return self._failed_update(now)
        return None

    def transition_resume_from_hitl(self) -> AtomicStatusTransition | None:
        if self.status != AgentRunStatus.AWAITING_HITL:
            return None
        return AtomicStatusTransition(
            expected=AgentRunStatus.AWAITING_HITL,
            new=AgentRunStatus.RUNNING,
        )

    def transition_repair_complete(self, now: datetime, *, promoted_on_main: bool) -> RunStatusUpdate | None:
        """Close a stuck ``running`` run when main already has promotion or row is stale."""
        if self.status != AgentRunStatus.RUNNING:
            return None
        if promoted_on_main or is_stale_active_run(self.created_at, now=now):
            return self._completed_update(now)
        return None

    def transition_reconcile_close(self, now: datetime) -> RunStatusUpdate | None:
        """Orphan cleanup before a new user turn."""
        if self.status == AgentRunStatus.AWAITING_HITL:
            return self._completed_update(now)
        if self.is_active and is_stale_active_run(self.created_at, now=now):
            return self._completed_update(now)
        return None
