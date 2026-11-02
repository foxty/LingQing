"""Resolve ``AgentRunPort`` from ``RunnableConfig``."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.agents.ports.agent_run_port import AgentRunPort


def resolve_agent_run_port(config: RunnableConfig) -> AgentRunPort:
    port = (config.get("configurable") or {}).get("agent_run_port")
    if port is None:
        raise ValidationError("configurable.agent_run_port is required for run-scoped agent I/O")
    return port  # type: ignore[return-value]
