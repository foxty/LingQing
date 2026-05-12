"""Core AgentConfig functionality tests."""

import pytest
import yaml

from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.system_agent_config import AgentConfigLoader, load_yaml_agent_config


def _manager(loader, agent_id=1, config_overrides=None):
    return AgentConfig(
        load_yaml_agent_config(agent_id, config_loader=loader),
        config_overrides=config_overrides,
    )


@pytest.fixture
def minimal_yaml(tmp_path):
    """Create minimal valid agents.yaml."""
    yaml_file = tmp_path / "agents.yaml"
    yaml_file.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": 1,
                        "name": "Test Agent",
                        "system_prompt": "Test prompt",
                        "default_tools": [],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return yaml_file


class TestAgentConfigBasics:
    """Test core config loading and property access."""

    def test_load_config_caches_result(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        # First call populates cache
        config1 = manager.get_config()
        # Second call returns same cached base (with overrides applied as copy)
        config2 = manager.get_config()

        # Both should have same values (overrides create copy but values match)
        assert config1 == config2
        # Cache is used (internal _config_cache is set)
        assert manager._config_cache is not None

    def test_config_overrides_applied(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader, config_overrides={"temperature": 0.9})

        config = manager.get_config()
        assert config["temperature"] == 0.9

    def test_property_accessors(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.agent_name == "Test Agent"
        assert manager.system_prompt == "Test prompt"
        assert manager.max_tokens == 2000
        assert manager.max_loop_iterations == 50

    def test_agent_id_not_found_raises(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))

        with pytest.raises(ValueError, match="Agent ID 999 not found"):
            load_yaml_agent_config(999, config_loader=loader)

    def test_optional_fields_return_none(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.temperature is None
        assert manager.top_p is None
        assert manager.frequency_penalty is None


class TestMiniAgentProperties:
    """Test mini-agent specific properties."""

    def test_mini_agent_classification(self, tmp_path):
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(
            yaml.safe_dump(
                {
                    "system_agents": {},
                    "mini_agents": {
                        "test_preset": {
                            "agent_id": 2,
                            "classification": "data_analysis",
                            "response_format": "json",
                        }
                    },
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        loader = AgentConfigLoader(config_path=str(yaml_file))
        manager = _manager(loader, agent_id=2)

        assert manager.classification == "data_analysis"
        assert manager.response_format == "json"

    def test_missing_mini_properties_return_none(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.classification is None
        assert manager.response_format is None


class TestGetProperty:
    """Test generic property access."""

    def test_get_existing_property(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.get_property("name") == "Test Agent"

    def test_get_missing_property_with_default(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.get_property("nonexistent", "default") == "default"

    def test_get_missing_property_without_default(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.get_property("nonexistent") is None

    def test_model_key_accessor(self, minimal_yaml):
        loader = AgentConfigLoader(config_path=str(minimal_yaml))
        manager = _manager(loader)

        assert manager.model_key() is None
