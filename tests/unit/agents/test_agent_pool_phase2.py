"""Tests for AgentPool consuming a resolved AgentLoadedConfig."""

import pytest

from apps.tenant_app_service.agent_pool import AgentPool
from apps.tenant_app_service.agents.system_agent_config import load_yaml_agent_config


@pytest.mark.asyncio
class TestAgentPoolWithResolvedConfig:
    """Test AgentPool.get_or_create_agent(config)."""

    async def test_get_or_create_agent_from_config(self):
        """Test creating agent by passing a loaded document."""
        pool = AgentPool()
        agent = await pool.get_or_create_agent(load_yaml_agent_config(-1))

        assert agent is not None
        assert hasattr(agent, "ainvoke")

    async def test_agent_pool_caches_agents(self):
        """Test that agents are cached and reused."""
        pool = AgentPool()
        config = load_yaml_agent_config(-1)

        agent1 = await pool.get_or_create_agent(config)
        agent2 = await pool.get_or_create_agent(config)

        assert agent1 is agent2

    async def test_agent_pool_with_config_overrides(self):
        """Test that config overrides are passed through."""
        pool = AgentPool()
        overrides = {"temperature": 0.5}

        agent = await pool.get_or_create_agent(
            load_yaml_agent_config(-1),
            config_overrides=overrides,
        )

        assert agent is not None
        assert hasattr(agent, "ainvoke")

    async def test_agent_pool_caches_variants_separately(self):
        """Test that agents with different overrides are cached separately."""
        pool = AgentPool()
        config = load_yaml_agent_config(-1)

        agent1 = await pool.get_or_create_agent(
            config,
            config_overrides={"temperature": 0.5},
        )
        agent2 = await pool.get_or_create_agent(
            config,
            config_overrides={"temperature": 0.7},
        )

        assert agent1 is not agent2

    async def test_agent_pool_missing_agent_id_raises_error(self):
        """Pool requires agent_id on the document."""
        pool = AgentPool()

        with pytest.raises(ValueError, match="agent_id"):
            await pool.get_or_create_agent({})

    async def test_agent_pool_multiple_agents(self):
        """Test creating multiple calls in the same pool."""
        pool = AgentPool()
        config = load_yaml_agent_config(-1)

        agent1 = await pool.get_or_create_agent(config)
        assert agent1 is not None

        agent1_again = await pool.get_or_create_agent(config)
        assert agent1_again is not None

        assert agent1 is agent1_again
