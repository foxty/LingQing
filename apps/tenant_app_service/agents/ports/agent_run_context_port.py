"""Run-scoped conversation I/O port slice (prompt load, persist, in-run summary rows).

Composed into :class:`AgentRunPort` with lifecycle and HITL; inject the unified port at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope


@dataclass(frozen=True, slots=True)
class RunSummaryRecord:
    summary_text: str
    cutoff_message_id: str | None


class AgentRunContextPort(Protocol):
    """Chat-owned: load/persist run transcript and in-run summary rows."""

    async def load_prompt_context(self, scope: AgentRunScope) -> list[BaseMessage]:
        """Thread summary, main-line tail, and this run's messages for graph merge."""

    async def persist_run_messages(
        self,
        scope: AgentRunScope,
        messages: list[BaseMessage],
        config: RunnableConfig,
        *,
        deduplicate: bool = True,
    ) -> None:
        """Save LangChain messages to ``agent_run_messages`` for this run."""

    async def get_in_run_summary(self, tenant_id: int, run_id: str) -> RunSummaryRecord | None: ...

    async def upsert_in_run_summary(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        run_id: str,
        summary_text: str,
        cutoff_message_id: str | None,
        through_agent_run_message_id: int | None,
    ) -> None: ...

    async def resolve_run_message_db_id(self, message_id: str, run_id: str) -> int | None: ...

    async def hydrate_prompt_messages(
        self,
        messages: list[BaseMessage],
        *,
        tenant_id: int,
        db: AsyncSession,
    ) -> list[BaseMessage]:
        """Apply read-time HITL resolution before prompt merge."""

    async def summarize_run_prefix(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        run_id: str,
        previous_summary: str | None,
        prefix_text: str,
    ) -> str | None:
        """LLM summary for in-run compact when over token budget."""
