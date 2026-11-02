"""Ports for agent harness (implemented by chat adapters).

**Chat → agent configurable contract** (when ``run_id`` is set on a turn):

- ``run_context_port`` (:class:`AgentRunContextPort`) — prompt load, run transcript persist,
  in-run summary read/write
- ``agent_run_lifecycle`` (:class:`AgentRunLifecycle`) — run status (HITL pause)
- ``run_id``, ``db_session``, ``runtime``, ``thread_id`` — identity and DB session
- ``skip_load_history`` — HITL/checkpoint resume; context port still required for persist

:class:`AgentRunScope` is the **run scope** (tenant/thread/run/agent keys) passed into port
methods. It is not the injectable in ``configurable``.

Agents must not import chat modules; only these ports and harness memory helpers.
"""

from apps.tenant_app_service.agents.ports.agent_run_context_port import AgentRunContextPort, RunSummaryRecord
from apps.tenant_app_service.agents.ports.run_lifecycle import AgentRunLifecycle
from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope

__all__ = [
    "AgentRunContextPort",
    "AgentRunLifecycle",
    "AgentRunScope",
    "RunSummaryRecord",
]
