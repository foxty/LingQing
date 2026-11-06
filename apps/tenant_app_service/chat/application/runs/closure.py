"""Unified run closure dispatcher (stream, reject, reconcile, cancel teardown)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.domain.agent_run.closure import RunClosureOutcome

logger = get_logger(__name__)


@dataclass(frozen=True)
class RunClosureRollup:
    """When to schedule cumulative thread roll-up after a turn ends."""

    session_id: str
    thread_id: str | None
    run_id: str | None = None


@dataclass(frozen=True)
class TerminalHitlRejectInput:
    """HITL → chat anti-corruption payload for reject run closure (no ORM in chat)."""

    proposal_id: str
    session_id: str | None
    thread_id: str
    agent_id: int
    requested_by: int
    tool_name: str | None
    assistant_ack_content: str


class RunClosureExecutor(Protocol):
    """Session-scoped run writes ``apply_run_closure`` needs (``ThreadRunService``)."""

    db: AsyncSession
    tenant_id: int

    async def mark_run_failed(self, run_id: str) -> None: ...

    async def mark_run_completed(self, run_id: str) -> None: ...

    async def finalize_run_for_main(self, run_id: str) -> None: ...


def schedule_run_closure_rollup(
    db: AsyncSession,
    tenant_id: int,
    *,
    session_id: str,
    thread_id: str | None,
    run_id: str | None = None,
) -> None:
    """Schedule cumulative thread roll-up after a turn completes."""
    if not thread_id:
        return
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    ChatTurnService(tenant_id, db).schedule_session_end(
        session_id=session_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def apply_run_closure(
    executor: RunClosureExecutor,
    *,
    run_id: str | None,
    outcome: RunClosureOutcome,
    rollup: RunClosureRollup | None = None,
) -> None:
    """Single entry for run status updates and main-timeline promotion after a turn ends."""
    if run_id:
        if outcome == RunClosureOutcome.PAUSED_FOR_HITL:
            logger.info("Agent run paused at HITL checkpoint run_id=%s", run_id)
        elif outcome == RunClosureOutcome.CANCELLED:
            logger.info("Agent run invoke ended cancelled run_id=%s", run_id)
        elif outcome == RunClosureOutcome.RECONCILED_BEFORE_NEW_TURN:
            logger.info("Agent run reconciled before new user turn run_id=%s", run_id)
            await executor.mark_run_completed(run_id)
        elif outcome == RunClosureOutcome.FAILED:
            await executor.mark_run_failed(run_id)
        elif outcome in (RunClosureOutcome.COMPLETED, RunClosureOutcome.TERMINAL_HITL_REJECT):
            await executor.finalize_run_for_main(run_id)

    if rollup is not None:
        schedule_run_closure_rollup(
            executor.db,
            executor.tenant_id,
            session_id=rollup.session_id,
            thread_id=rollup.thread_id,
            run_id=rollup.run_id,
        )
