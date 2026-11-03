"""Run lifecycle port (status transitions owned by chat)."""

from __future__ import annotations

from typing import Protocol


class AgentRunLifecycle(Protocol):
    """Chat-owned adapter for agent run status (e.g. HITL pause)."""

    async def mark_run_awaiting_hitl(self, run_id: str) -> None: ...

    async def is_run_cancelled(self, run_id: str) -> bool: ...
