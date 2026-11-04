"""Chat adapter: run-scoped prompt context and in-run summary persistence."""

from __future__ import annotations

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agents.ports.agent_run_context_port import AgentRunContextPort, RunSummaryRecord
from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope
from apps.tenant_app_service.chat.conversation_memory_manager import ConversationMemoryManager
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_message_repository import (
    AgentRunMessageRepository,
)
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_summary_repository import (
    AgentRunSummaryRepository,
)
from apps.tenant_app_service.chat.service_base import (
    DEFAULT_MAIN_TIMELINE_TURN_LIMIT,
    RUN_HISTORY_MESSAGE_LIMIT,
)


class ChatRunContextAdapter:
    """Implements :class:`AgentRunContextPort` for one agent run."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        run_id: str,
    ) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._agent_id = agent_id
        self._run_id = run_id
        self._summary_repo = AgentRunSummaryRepository(db)
        self._message_repo = AgentRunMessageRepository(db)

    def _manager(self, scope: AgentRunScope) -> ConversationMemoryManager:
        return ConversationMemoryManager(
            db_session=self._db,
            thread_id=scope.thread_id,
            tenant_id=scope.tenant_id,
            agent_id=scope.agent_id,
            run_id=scope.run_id,
        )

    async def load_prompt_context(self, scope: AgentRunScope) -> list[BaseMessage]:
        return await self._manager(scope).load_messages_with_summary(
            main_timeline_turn_limit=DEFAULT_MAIN_TIMELINE_TURN_LIMIT,
            run_message_limit=RUN_HISTORY_MESSAGE_LIMIT,
        )

    async def persist_run_messages(
        self,
        scope: AgentRunScope,
        messages: list[BaseMessage],
        config: RunnableConfig,
        *,
        deduplicate: bool = True,
    ) -> None:
        await self._manager(scope).add_messages(messages, config, deduplicate=deduplicate)

    async def get_in_run_summary(self, tenant_id: int, run_id: str) -> RunSummaryRecord | None:
        row = await self._summary_repo.get_for_run(tenant_id, run_id)
        if row is None or not row.summary_text:
            return None
        return RunSummaryRecord(
            summary_text=row.summary_text,
            cutoff_message_id=row.cutoff_message_id,
        )

    async def upsert_in_run_summary(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        run_id: str,
        summary_text: str,
        cutoff_message_id: str | None,
        through_agent_run_message_id: int | None,
    ) -> None:
        await self._summary_repo.upsert(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            summary_text=summary_text,
            cutoff_message_id=cutoff_message_id,
            through_agent_run_message_id=through_agent_run_message_id,
        )

    async def resolve_run_message_db_id(self, message_id: str, run_id: str) -> int | None:
        row = await self._message_repo.get_message_by_message_id(message_id)
        if row is None or row.run_id != run_id:
            return None
        return row.id

    async def hydrate_prompt_messages(
        self,
        messages: list[BaseMessage],
        *,
        tenant_id: int,
        db: AsyncSession,
    ) -> list[BaseMessage]:
        return messages

    async def summarize_run_prefix(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        run_id: str,
        previous_summary: str | None,
        prefix_text: str,
    ) -> str | None:
        return None


def chat_run_context_adapter_for_run(
    *,
    db: AsyncSession,
    tenant_id: int,
    agent_id: int,
    run_id: str,
) -> AgentRunContextPort:
    """Build context-only adapter (tests / internal); production uses ``ChatAgentRunPort``."""
    return ChatRunContextAdapter(
        db=db,
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_id=run_id,
    )
