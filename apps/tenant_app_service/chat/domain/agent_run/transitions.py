"""Status transition value objects (aggregate → persistence)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.tenant_app_service.chat.domain.agent_run.status import AgentRunStatus


@dataclass(frozen=True)
class RunStatusUpdate:
    status: AgentRunStatus
    completed_at: datetime | None = None


@dataclass(frozen=True)
class AtomicStatusTransition:
    expected: AgentRunStatus
    new: AgentRunStatus
