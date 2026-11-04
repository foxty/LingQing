"""Agent run status vocabulary (value objects)."""

from __future__ import annotations

from enum import StrEnum


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_HITL = "awaiting_hitl"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_AGENT_RUN_STATUSES: frozenset[str] = frozenset(
    {
        AgentRunStatus.QUEUED,
        AgentRunStatus.RUNNING,
        AgentRunStatus.AWAITING_HITL,
    }
)

TERMINAL_AGENT_RUN_STATUSES: frozenset[str] = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)

CANCELLABLE_AGENT_RUN_STATUSES: frozenset[str] = frozenset(
    {
        AgentRunStatus.QUEUED,
        AgentRunStatus.RUNNING,
        AgentRunStatus.AWAITING_HITL,
    }
)
