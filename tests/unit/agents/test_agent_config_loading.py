"""Tests for resolved-config construction of AgentBase.

Call sites load YAML (or pass a catalog overlay). AgentBase only consumes the document.
"""

import pytest

from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.system_agent_config import load_yaml_agent_config


@pytest.mark.asyncio
class TestAgentConfigLoading:
    """Test AgentBase(config) after YAML load."""

    async def test_init_loads_system_agent(self):
        """Test loading Agent One from YAML, then constructing the graph class."""
        config = load_yaml_agent_config(-1)
        agent = AgentBase(config)

        assert agent is not None
        assert isinstance(agent, AgentBase)
        assert agent.agent_id == -1
        assert agent.agent_name == "Agent One"
        assert agent.agent_config.system_prompt is not None

    async def test_yaml_loader_invalid_agent_raises_error(self):
        """Unknown YAML ids fail at the loader, not inside AgentBase."""
        with pytest.raises(ValueError, match="Agent ID"):
            load_yaml_agent_config(99999)

    async def test_init_with_config_overrides(self):
        """Test that config_overrides are applied correctly."""
        overrides = {
            "temperature": 0.7,
            "max_loop_iterations": 5,
        }

        agent = AgentBase(load_yaml_agent_config(-1), config_overrides=overrides)

        assert agent.agent_config.temperature == 0.7
        assert agent.agent_config.max_loop_iterations == 5
        assert agent.agent_id == -1

    async def test_init_applies_name_and_model_profile_overrides(self):
        """Test that __init__ overlays name/prompt/model profile on the locked document."""
        agent = AgentBase(
            load_yaml_agent_config(-1),
            config_overrides={
                "name": "TestAgent",
                "system_prompt": "Test prompt",
                "model_profile_id": 42,
            },
        )

        assert agent.agent_id == -1
        assert agent.agent_name == "TestAgent"
        assert agent.agent_config.model_profile_id() == 42

    async def test_init_returns_configured_agent(self):
        """Test that AgentBase(config) returns a fully configured agent."""
        agent = AgentBase(load_yaml_agent_config(-1))

        assert hasattr(agent, "agent_config")
        assert hasattr(agent, "logger")

    async def test_config_loaded_from_agents_yaml_has_tools(self):
        """Test that loaded config includes tools from agents.yaml."""
        agent = AgentBase(load_yaml_agent_config(-1))

        tools = agent.agent_config.get_tools()
        assert len(tools) > 0
        tool_names = {tool.name for tool in tools}
        assert "load_skill" in tool_names
        assert "search_documents" in tool_names or "search_data_assets" in tool_names
        assert "retrieve_resource_context" in tool_names
