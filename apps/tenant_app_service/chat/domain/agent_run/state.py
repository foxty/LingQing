"""Immutable agent run state (entity snapshot at repository boundary)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AgentRunState:
    id: str
    tenant_id: int
    thread_id: str
    agent_id: int
    trigger_message_id: str
    invoke_index: int
    status: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


# Deprecated name; prefer AgentRunState or AgentRun aggregate.
AgentRunDomain = AgentRunState
