"""Polling session status vocabulary and pure time rules (no I/O).

Used by session status resolution, turn admission, and run reconciliation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

SESSION_STATUS_RUNNING: Final = "running"
SESSION_STATUS_AWAITING_HITL: Final = "awaiting_hitl"
SESSION_STATUS_HITL_APPROVED_PENDING_CONTINUE: Final = "hitl_approved_pending_continue"
SESSION_STATUS_COMPLETED: Final = "completed"

# Orphaned runs (e.g. server reload after human persist) stop polling after this window.
SESSION_STALE_RUNNING_SECONDS: Final = 900


def is_stale_running_session(
    started_at: datetime | None,
    *,
    stale_after_seconds: int = SESSION_STALE_RUNNING_SECONDS,
    now: datetime | None = None,
) -> bool:
    """True when a running/pending UI session should be treated as finished for polling."""
    if started_at is None:
        return False
    current = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return current - started_at > timedelta(seconds=stale_after_seconds)
