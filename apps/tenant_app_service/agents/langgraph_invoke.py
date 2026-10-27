"""LangGraph invoke outcomes (checkpoint interrupt detection)."""

from __future__ import annotations

from enum import StrEnum


class AgentInvokeOutcome(StrEnum):
    INTERRUPTED_FOR_HITL = "interrupted_for_hitl"
    COMPLETED = "completed"
    FAILED = "failed"


async def invoke_has_pending_interrupt(agent_graph, config: dict) -> bool:
    """True when LangGraph paused on an interrupt (e.g. HITL gate)."""
    state = await agent_graph.aget_state(config)
    if state.interrupts:
        return True
    for task in state.tasks or ():
        if getattr(task, "interrupts", None):
            return True
    return False


async def classify_invoke_outcome(agent_graph, config: dict) -> AgentInvokeOutcome:
    if await invoke_has_pending_interrupt(agent_graph, config):
        return AgentInvokeOutcome.INTERRUPTED_FOR_HITL
    return AgentInvokeOutcome.COMPLETED
