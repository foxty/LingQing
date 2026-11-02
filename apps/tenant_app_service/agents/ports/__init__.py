"""Ports for agent harness (implemented by chat adapters).

**Chat → agent configurable contract** (when ``run_id`` is set on a turn):

- ``agent_run_port`` (:class:`AgentRunPort`) — prompt load/persist, in-run summaries,
  HITL hydration + tool gate, run lifecycle
- ``run_id``, ``db_session``, ``runtime``, ``thread_id`` — identity and DB session
- ``skip_load_history`` — HITL/checkpoint resume; run port still required for persist

:class:`AgentRunScope` is run identity (keys) passed into port methods.

LangGraph checkpoints are configured at graph compile time — not on this port.

Agents must not import chat or hitl modules; only these ports and harness helpers.
"""

from apps.tenant_app_service.agents.ports.agent_run_context_port import AgentRunContextPort, RunSummaryRecord
from apps.tenant_app_service.agents.ports.agent_run_port import AgentRunPort
from apps.tenant_app_service.agents.ports.resolve_agent_run_port import resolve_agent_run_port
from apps.tenant_app_service.agents.ports.run_lifecycle import AgentRunLifecycle
from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope
from apps.tenant_app_service.agents.ports.tool_hitl import ToolHitlDecision

__all__ = [
    "AgentRunContextPort",
    "AgentRunLifecycle",
    "AgentRunPort",
    "AgentRunScope",
    "RunSummaryRecord",
    "ToolHitlDecision",
    "resolve_agent_run_port",
]
