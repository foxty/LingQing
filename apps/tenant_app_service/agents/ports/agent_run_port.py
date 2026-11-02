"""Unified injectable port: context I/O + run lifecycle + tool HITL.

:class:`AgentRunContextPort` is the transcript/summary slice; this type is what chat wires
as ``configurable.agent_run_port`` (see :class:`ChatAgentRunPort`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from apps.tenant_app_service.agents.ports.agent_run_context_port import AgentRunContextPort
from apps.tenant_app_service.agents.ports.run_lifecycle import AgentRunLifecycle
from apps.tenant_app_service.agents.ports.tool_hitl import ToolHitlPort


@runtime_checkable
class AgentRunPort(AgentRunContextPort, AgentRunLifecycle, ToolHitlPort, Protocol):
    """Single injectable adapter for everything chat-owned on an agent run."""
