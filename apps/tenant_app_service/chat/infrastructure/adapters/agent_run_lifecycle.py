"""Chat adapter: agent run lifecycle (status) for the harness."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agents.ports.run_lifecycle import AgentRunLifecycle
from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService


class ChatAgentRunLifecycle:
    """Marks run status via ``ThreadRunService`` (tenant-scoped)."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._service = ThreadRunService(db, tenant_id)

    async def mark_run_awaiting_hitl(self, run_id: str) -> None:
        await self._service.mark_run_awaiting_hitl(run_id)

    async def is_run_cancelled(self, run_id: str) -> bool:
        return await self._service.is_run_cancelled(run_id)


def chat_agent_run_lifecycle(db: AsyncSession, tenant_id: int) -> AgentRunLifecycle:
    """Lifecycle-only adapter factory (unit tests); production uses ``ChatAgentRunPort``."""
    return ChatAgentRunLifecycle(db, tenant_id)
