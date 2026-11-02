"""Chat-side HITL tool gate (used by :class:`ChatAgentRunPort`)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.agents.domain import AgentRuntimeContext, ToolConfig
from apps.tenant_app_service.agents.ports.tool_hitl import HITL_ACTION_REQUIRE_HITL, ToolHitlDecision
from apps.tenant_app_service.hitl.domain import (
    HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
    HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
    HITL_STATUS_APPROVED,
    HITL_STATUS_EXECUTED,
    HITL_STATUS_REJECTED,
)
from apps.tenant_app_service.hitl.policy_engine import evaluate_approval_decision
from apps.tenant_app_service.hitl.service import HitlApprovalService
from apps.tenant_app_service.hitl.utils import build_hitl_gate_tool_content


class ChatHitlToolGate:
    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    def evaluate_tool_approval(self, tool_config: ToolConfig | None) -> ToolHitlDecision:
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
        if decision.action != HITL_ACTION_REQUIRE_HITL:
            return None, None

        db_session = config.get("configurable", {}).get("db_session") or self._db
        approval_service = HitlApprovalService(runtime.user.tenant_id, db_session)
        configured_proposal_id = config.get("configurable", {}).get("hitl_proposal_id")
        if configured_proposal_id:
            proposal_id = str(configured_proposal_id)
        else:
            proposal_id = approval_service.build_proposal_id(
                thread_id=runtime.thread_id,
                session_id=runtime.session_id,
                tool_name=tool_name,
                tool_args=tool_args,
            )
        approval = await approval_service.get_or_create_pending(
            tenant_id=runtime.user.tenant_id,
            thread_id=runtime.thread_id,
            session_id=runtime.session_id,
            agent_id=runtime.agent_id,
            proposal_id=proposal_id,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=decision.risk_level,
            requested_by=runtime.user.user_id,
        )

        if approval.status == HITL_STATUS_APPROVED:
            return None, proposal_id

        if approval.status == HITL_STATUS_EXECUTED:
            return (
                ToolMessage(
                    id=str(uuid4()),
                    content=f"Tool '{tool_name}' already executed for approved proposal.",
                    tool_call_id=tool_call_id,
                    additional_kwargs={
                        **additional_kwargs,
                        "hitl": {
                            "type": HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
                            "proposal_id": proposal_id,
                        },
                    },
                ),
                proposal_id,
            )

        if approval.status == HITL_STATUS_REJECTED:
            return (
                ToolMessage(
                    id=str(uuid4()),
                    content=f"Tool '{tool_name}' was rejected by approver.",
                    tool_call_id=tool_call_id,
                    additional_kwargs={
                        **additional_kwargs,
                        "hitl": {
                            "type": HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
                            "proposal_id": proposal_id,
                        },
                    },
                ),
                proposal_id,
            )

        return (
            ToolMessage(
                id=str(uuid4()),
                content=build_hitl_gate_tool_content(tool_name),
                tool_call_id=tool_call_id,
                additional_kwargs={
                    **additional_kwargs,
                    "hitl": {
                        "type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
                        "proposal_id": proposal_id,
                    },
                },
            ),
            proposal_id,
        )

    @asynccontextmanager
    async def hitl_tool_execution_guard(self, proposal_id: str) -> AsyncIterator[None]:
        approval_service = HitlApprovalService(self._tenant_id, self._db)
        async with approval_service.execution_state_manager(proposal_id):
            yield
