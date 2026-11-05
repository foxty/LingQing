"""Map LangGraph stream outcomes to chat run-closure policy."""

from __future__ import annotations

from apps.tenant_app_service.agents.langgraph_invoke import AgentInvokeOutcome
from apps.tenant_app_service.chat.domain.agent_run.closure import RunClosureOutcome


def closure_outcome_from_invoke(outcome: AgentInvokeOutcome) -> RunClosureOutcome:
    """Translate adapter invoke result into chat closure policy.

    ``AgentInvokeOutcome`` is stream/checkpoint vocabulary (agents layer).
    ``RunClosureOutcome`` is chat lifecycle vocabulary (promote, fail, pause, rollup).
    They differ: e.g. reject uses ``TERMINAL_HITL_REJECT`` which never comes from the graph,
    and ``INTERRUPTED_FOR_HITL`` maps to ``PAUSED_FOR_HITL`` (no promotion yet).
    """
    if outcome == AgentInvokeOutcome.COMPLETED:
        return RunClosureOutcome.COMPLETED
    if outcome == AgentInvokeOutcome.CANCELLED:
        return RunClosureOutcome.CANCELLED
    if outcome == AgentInvokeOutcome.FAILED:
        return RunClosureOutcome.FAILED
    if outcome == AgentInvokeOutcome.INTERRUPTED_FOR_HITL:
        return RunClosureOutcome.PAUSED_FOR_HITL
    raise ValueError(f"unsupported invoke outcome: {outcome!r}")
