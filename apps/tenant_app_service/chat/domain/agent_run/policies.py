"""Stateless agent-run policies (domain services)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from apps.tenant_app_service.chat.domain.agent_run.status import AgentRunStatus

RUN_STALE_ACTIVE_SECONDS: Final = 900


def run_status_allows_thread_rollup(status: str) -> bool:
    """Whether a finished run may roll into the cumulative thread summary."""
    return status in (
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
    )


def is_stale_active_run(
    started_at: datetime | None,
    *,
    stale_after_seconds: int = RUN_STALE_ACTIVE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """True when an ACTIVE run row should be treated as abandoned for repair."""
    if started_at is None:
        return False
    current = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return current - started_at > timedelta(seconds=stale_after_seconds)
