"""How an agent run turn ends from the product's perspective (not persisted status alone)."""

from __future__ import annotations

from enum import StrEnum


class RunClosureOutcome(StrEnum):
    """Terminal or pausing resolution for run closure policy (promotion, rollup, status)."""

    COMPLETED = "completed"
    TERMINAL_HITL_REJECT = "terminal_hitl_reject"
    RECONCILED_BEFORE_NEW_TURN = "reconciled_before_new_turn"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PAUSED_FOR_HITL = "paused_for_hitl"
