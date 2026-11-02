"""Run scope: tenant/thread/run/agent keys for port method calls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentRunScope:
    """Which run's data to load or persist (not the injectable port)."""

    tenant_id: int
    thread_id: str
    run_id: str
    agent_id: int
