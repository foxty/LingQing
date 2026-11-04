"""Chat adapter implementing :class:`AgentRunPort` for one agent run."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.session import app_db_session
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, ToolConfig
from apps.tenant_app_service.agents.ports.agent_run_port import AgentRunPort
from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope
from apps.tenant_app_service.agents.ports.tool_hitl import ToolHitlDecision
from apps.tenant_app_service.chat.hitl_tool_gate import ChatHitlToolGate
from apps.tenant_app_service.chat.infrastructure.adapters.agent_run_lifecycle import ChatAgentRunLifecycle
from apps.tenant_app_service.chat.infrastructure.adapters.run_context_adapter import ChatRunContextAdapter


class ChatAgentRunPort:
    """Context I/O, lifecycle, HITL tool gate — one DB session per port call."""

    def __init__(
        self,
        *,
        tenant_id: int,
        agent_id: int,
        run_id: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._agent_id = agent_id
        self._run_id = run_id

    @asynccontextmanager
    async def _db(self) -> AsyncIterator[AsyncSession]:
        async with app_db_session() as session:
            yield session

    def _context(self, db: AsyncSession) -> ChatRunContextAdapter:
        return ChatRunContextAdapter(
            db=db,
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            run_id=self._run_id,
        )

    def _lifecycle(self, db: AsyncSession) -> ChatAgentRunLifecycle:
        return ChatAgentRunLifecycle(db, self._tenant_id)

    def _hitl(self, db: AsyncSession) -> ChatHitlToolGate:
        return ChatHitlToolGate(db, self._tenant_id)

    async def load_prompt_context(self, scope: AgentRunScope) -> list[BaseMessage]:
        async with self._db() as db:
            return await self._context(db).load_prompt_context(scope)

    async def persist_run_messages(
        self,
        scope: AgentRunScope,
        messages: list[BaseMessage],
        config: RunnableConfig,
        *,
        deduplicate: bool = True,
    ) -> None:
        async with self._db() as db:
            await self._context(db).persist_run_messages(
                scope, messages, config, deduplicate=deduplicate
            )

    async def get_in_run_summary(self, tenant_id: int, run_id: str):
        async with self._db() as db:
            return await self._context(db).get_in_run_summary(tenant_id, run_id)

    async def upsert_in_run_summary(self, **kwargs) -> None:
        async with self._db() as db:
            await self._context(db).upsert_in_run_summary(**kwargs)

    async def resolve_run_message_db_id(self, message_id: str, run_id: str):
        async with self._db() as db:
            return await self._context(db).resolve_run_message_db_id(message_id, run_id)

    async def hydrate_prompt_messages(
        self,
        messages: list[BaseMessage],
        *,
        tenant_id: int,
        db: AsyncSession | None = None,
    ) -> list[BaseMessage]:
        from apps.tenant_app_service.hitl.history import hydrate_hitl_history_messages

        if db is not None:
            return await hydrate_hitl_history_messages(messages, tenant_id=tenant_id, db=db)
        async with self._db() as session:
            return await hydrate_hitl_history_messages(messages, tenant_id=tenant_id, db=session)

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

        async with self._db() as db:
            return await MiniAgentService.create(db, tenant_id).summarize_run_prefix(
                thread_id=thread_id,
                run_id=run_id,
                previous_summary=previous_summary,
                prefix_text=prefix_text,
            )

    async def mark_run_awaiting_hitl(self, run_id: str) -> None:
        async with self._db() as db:
            await self._lifecycle(db).mark_run_awaiting_hitl(run_id)

    async def is_run_cancelled(self, run_id: str) -> bool:
        async with self._db() as db:
            return await self._lifecycle(db).is_run_cancelled(run_id)

    def evaluate_tool_approval(self, tool_config: ToolConfig | None) -> ToolHitlDecision:
        from apps.tenant_app_service.hitl.policy_engine import evaluate_approval_decision

        decision = evaluate_approval_decision(tool_config)
        return ToolHitlDecision(
            action=decision.action,
            reason=decision.reason,
            risk_level=getattr(decision, "risk_level", "medium"),
        )

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
        async with self._db() as db:
            return await self._hitl(db).gate_tool_call(
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
        async with self._db() as db:
            async with self._hitl(db).hitl_tool_execution_guard(proposal_id):
                yield


def chat_agent_run_port_for_run(
    *,
    tenant_id: int,
    agent_id: int,
    run_id: str,
) -> AgentRunPort:
    """Factory wired into ``RunnableConfig.agent_run_port`` by turn orchestration."""
    return ChatAgentRunPort(
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_id=run_id,
    )