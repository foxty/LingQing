"""Repository port for agent runs (domain layer — no SQLAlchemy)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from apps.tenant_app_service.chat.domain.agent_run.state import AgentRunState
from apps.tenant_app_service.chat.domain.agent_run.status import AgentRunStatus


class AgentRunRepositoryPort(Protocol):
    async def create_run(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        agent_id: int,
        trigger_message_id: str,
        invoke_index: int,
        session_id: str,
        status: str = AgentRunStatus.QUEUED,
    ) -> AgentRunState: ...

    async def get_run(self, tenant_id: int, run_id: str) -> AgentRunState | None: ...

    async def get_by_session_id(self, session_id: str) -> AgentRunState | None: ...

    async def set_status(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        completed_at: datetime | None = None,
    ) -> None: ...

    async def cancel_active_run(
        self,
        tenant_id: int,
        run_id: str,
        *,
        completed_at: datetime,
    ) -> AgentRunState | None: ...

    async def transition_status(
        self,
        run_id: str,
        *,
        expected: AgentRunStatus,
        new: AgentRunStatus,
    ) -> bool: ...

    async def list_active_for_thread_agent(self, thread_id: str, agent_id: int) -> list[AgentRunState]: ...

    async def list_for_thread(self, thread_id: str) -> list[AgentRunState]: ...

    async def list_for_trigger(self, thread_id: str, trigger_message_id: str) -> list[AgentRunState]: ...

    async def get_latest_for_thread_agent(self, thread_id: str, agent_id: int) -> AgentRunState | None: ...

    async def list_for_triggers(
        self,
        thread_id: str,
        trigger_message_ids: list[str],
    ) -> dict[str, list[AgentRunState]]: ...

    async def list_runs_for_history_page(
        self,
        *,
        thread_id: str,
        agent_id: int,
        session_limit: int,
        before_session_id: str | None,
        session_id: str | None,
    ) -> tuple[list[AgentRunState], bool, str | None]: ...

    async def count_active_for_thread(self, thread_id: str, agent_id: int | None = None) -> int: ...
