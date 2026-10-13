"""Tests for materializing system agent tool definitions from platform specs."""

import yaml

from apps.tenant_app_service.agents.system_agent_config import AgentConfigLoader, load_yaml_agent_config


def test_materialize_resolves_name_only_default_tools(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "platform": {
                    "tool_specs": {
                        "search_documents": {"limit": 5, "cacheable": True},
                        "load_skill": {"limit": 10},
                    }
                },
                "system_agents": {
                    "agent_one": {
                        "agent_id": -1,
                        "name": "Agent One",
                        "system_prompt": "Role",
                        "default_tools": ["search_documents", "load_skill"],
                    }
                },
                "mini_agents": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loader = AgentConfigLoader(config_path=str(agents_yaml))
    loader.get_platform_tool_specs()

    materialized = loader.materialize_system_agent_document(
        loader.get_system_agent_config(-1, materialize=False) or {}
    )
    by_name = {item["name"]: item for item in materialized["default_tools"]}
    assert by_name["search_documents"]["limit"] == 5
    assert by_name["search_documents"]["cacheable"] is True
    assert by_name["load_skill"]["limit"] == 10
    assert materialized["prompt_mode"] == "platform"


def test_load_yaml_agent_config_materializes_agent_one():
    config = load_yaml_agent_config(-1)
    names = {item["name"] for item in config.get("default_tools", [])}
    assert "search_documents" in names
    search = next(item for item in config["default_tools"] if item["name"] == "search_documents")
    assert search.get("limit") == 5


def test_load_mini_agent_yaml_uses_standalone_prompt_mode():
    config = load_yaml_agent_config(-101)
    assert config.get("prompt_mode") == "standalone"


def test_mini_agent_skips_platform_baseline_compose():
    from apps.tenant_app_service.agents.agent_config import AgentConfig

    config = load_yaml_agent_config(-101)
    manager = AgentConfig(config)
    assert manager._should_compose_platform_baseline() is False
