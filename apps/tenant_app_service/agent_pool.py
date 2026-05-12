"""Agent Pool Manager for Multi-Tenant Agent Instances.

Manages a pool of agent instances configured per tenant and agent config.
Creates and caches agent instances with tenant-specific configurations.

This module follows SOLID principles:
- Single Responsibility: Only manages agent lifecycle (create, cache)
- Open/Closed: Open for adding new agent types, closed for modification
- Dependency Inversion: Depends on agent factory functions, not concrete implementations

Architecture:
- Agent instances are now stateless (no context bound at creation)
- Configuration is passed via runtime context at invocation time
- This allows true reusability of agent instances across contexts
- DynamicAgent is used for role-based agents (multiple roles with dynamic switching)
- AgentBase is used for legacy agents (single static role/prompt)
"""

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents import AgentBase
from apps.tenant_app_service.agents.domain import AgentLoadedConfig

logger = get_logger(__name__)


class AgentPool:
    """Manages a pool of compiled agent graphs keyed by ``(agent_id, revision)``."""

    def __init__(self):
        """Initialize the agent pool."""
        self._pool: dict[str, Any] = {}
        logger.info("Agent pool initialized")

    async def get_or_create_agent(
        self,
        config: AgentLoadedConfig,
        *,
        config_overrides: dict | None = None,
        cache_revision: str | None = None,
    ) -> "CompiledStateGraph":
        """Get or create a compiled agent graph from a resolved document.

        Args:
            config: YAML-shaped agent document. Callers load YAML or overlay catalog.
            config_overrides: Optional dict to override specific config values
            cache_revision: Cache key suffix (custom-agent ``updated_at``)

        Returns:
            Compiled agent instance configured and ready to use
        """
        if "agent_id" not in config:
            raise ValueError("AgentLoadedConfig requires agent_id")
        agent_id = int(config["agent_id"])

        overrides = dict(config_overrides or {})
        if "max_loop_iterations" not in overrides:
            overrides["max_loop_iterations"] = 50

        agent_key = f"agent_{agent_id}"
        if cache_revision:
            agent_key = f"{agent_key}_{cache_revision}"
        elif config_overrides:
            override_key = "_".join(f"{k}={v}" for k, v in sorted(config_overrides.items()))
            agent_key = f"{agent_key}_{override_key}"

        if agent_key in self._pool:
            logger.info(f"Using cached agent: {agent_key}")
            return self._pool[agent_key]

        logger.info("Creating agent from config: agent_id=%s", agent_id)
        agent = AgentBase(config, config_overrides=overrides)
        logger.info(f"Agent created: {agent.agent_name}(agent_id={agent.agent_id})")
        graph = await agent.compile()
        self._pool[agent_key] = graph
        return graph


# Global agent pool instance
_agent_pool: AgentPool | None = None


def get_agent_pool() -> AgentPool:
    """Get the global agent pool instance.

    Returns:
        AgentPool instance
    """
    global _agent_pool
    if _agent_pool is None:
        _agent_pool = AgentPool()
    return _agent_pool
