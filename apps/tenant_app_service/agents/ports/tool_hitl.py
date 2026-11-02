"""Tool HITL gate port surface (implemented by chat adapter)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.domain import AgentRuntimeContext, ToolConfig

HITL_ACTION_ALLOW = "allow"
HITL_ACTION_DENY = "deny"
HITL_ACTION_REQUIRE_HITL = "require_hitl"


@dataclass(frozen=True, slots=True)
class ToolHitlDecision:
    action: str
    reason: str
    risk_level: str = "medium"


class ToolHitlPort(Protocol):
    """Human-in-the-loop tool gating (chat-owned implementation)."""

    def evaluate_tool_approval(self, tool_config: ToolConfig | None) -> ToolHitlDecision: ...

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
        """Return gate ToolMessage when execution must pause; else (None, proposal_id)."""

    @asynccontextmanager
    async def hitl_tool_execution_guard(self, proposal_id: str) -> AsyncIterator[None]: ...
