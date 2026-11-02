"""Chat adapter implementing :class:`AgentRunPort` for one agent run."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agents.domain import AgentRuntimeContext, ToolConfig
from apps.tenant_app_service.agents.ports.agent_run_port import AgentRunPort
from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope
from apps.tenant_app_service.agents.ports.tool_hitl import ToolHitlDecision
from apps.tenant_app_service.chat.agent_run_lifecycle import ChatAgentRunLifecycle
from apps.tenant_app_service.chat.hitl_tool_gate import ChatHitlToolGate
from apps.tenant_app_service.chat.run_context_adapter import ChatRunContextAdapter


class ChatAgentRunPort:
    """Context I/O, lifecycle, HITL tool gate, and summarization for the harness."""

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
        self._context = ChatRunContextAdapter(
            db=db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            run_id=run_id,
        )
        self._lifecycle = ChatAgentRunLifecycle(db, tenant_id)
        self._hitl = ChatHitlToolGate(db, tenant_id)

    async def load_prompt_context(self, scope: AgentRunScope) -> list[BaseMessage]:
        return await self._context.load_prompt_context(scope)

    async def persist_run_messages(
        self,
        scope: AgentRunScope,
        messages: list[BaseMessage],
        config: RunnableConfig,
        *,
        deduplicate: bool = True,
    ) -> None:
        await self._context.persist_run_messages(scope, messages, config, deduplicate=deduplicate)

    async def get_in_run_summary(self, tenant_id: int, run_id: str):
        return await self._context.get_in_run_summary(tenant_id, run_id)

    async def upsert_in_run_summary(self, **kwargs) -> None:
        await self._context.upsert_in_run_summary(**kwargs)

    async def resolve_run_message_db_id(self, message_id: str, run_id: str):
        return await self._context.resolve_run_message_db_id(message_id, run_id)

    async def hydrate_prompt_messages(
        self,
        messages: list[BaseMessage],
        *,
        tenant_id: int,
        db: AsyncSession,
    ) -> list[BaseMessage]:
        from apps.tenant_app_service.hitl.history import hydrate_hitl_history_messages

        return await hydrate_hitl_history_messages(messages, tenant_id=tenant_id, db=db)

    async def summarize_run_prefix(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        run_id: str,
        previous_summary: str | None,
        prefix_text: str,
    ) -> str | None:
        from apps.tenant_app_service.agents.mini_agent import MiniAgentService

        return await MiniAgentService.create(self._db, tenant_id).summarize_run_prefix(
            thread_id=thread_id,
            run_id=run_id,
            previous_summary=previous_summary,
            prefix_text=prefix_text,
        )

    async def mark_run_awaiting_hitl(self, run_id: str) -> None:
        await self._lifecycle.mark_run_awaiting_hitl(run_id)

    def evaluate_tool_approval(self, tool_config: ToolConfig | None) -> ToolHitlDecision:
        return self._hitl.evaluate_tool_approval(tool_config)

    async def gate_tool_call(
        self,
        *,
        runtime: AgentRuntimeContext,
        config: RunnableConfig,
        tool_name: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        decision: ToolHitlDecision,
        additional_kwargs: dict[str, Any],
    ) -> tuple[ToolMessage | None, str | None]:
        return await self._hitl.gate_tool_call(
            runtime=runtime,
            config=config,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_args=tool_args,
            decision=decision,
            additional_kwargs=additional_kwargs,
        )

    @asynccontextmanager
    async def hitl_tool_execution_guard(self, proposal_id: str) -> AsyncIterator[None]:
        async with self._hitl.hitl_tool_execution_guard(proposal_id):
            yield


def chat_agent_run_port_for_run(
    *,
    db: AsyncSession,
    tenant_id: int,
    agent_id: int,
    run_id: str,
) -> AgentRunPort:
    """Factory wired into ``RunnableConfig.agent_run_port`` by turn orchestration."""
    return ChatAgentRunPort(
        db=db,
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_id=run_id,
    )
