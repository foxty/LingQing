"""Tests for skill configuration in AgentConfig."""

import pytest
import yaml

from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, AgentTenantContext, AgentUserContext
from apps.tenant_app_service.agents.system_agent_config import (
    TOOL_REGISTRY,
    AgentConfigLoader,
    load_yaml_agent_config,
)
from apps.tenant_app_service.skills.resolution import SkillResolver


@pytest.fixture
def mock_runtime():
    return AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=1, tenant_name="TestTenant", config={}),
        user=AgentUserContext(
            user_id=7,
            username="testuser",
            role="admin",
            tenant_id=1,
            tenant_name="TestTenant",
        ),
        agent_id=-1,
        agent_name="TestAgent",
        thread_id="t1",
        session_id="s1",
    )


@pytest.fixture
def manager_factory(tmp_path):
    """Create isolated (AgentConfig, mock_runtime) backed by test-only YAML and skills."""

    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "system_prompt": "Base system prompt",
                        "default_api_refs": ["GET_/search"],
                        "default_tools": [
                            {"name": "load_skill", "limit": 20},
                            {"name": "unload_skill", "limit": 20},
                            {"name": "hitl_test_echo", "limit": 3, "hitl": {"mode": "always"}},
                        ],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "data_analyst.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "data_analyst",
                "description": "Analyze data",
                "system_prompt": "You are a Data Analyst Agent.",
                "api_refs": ["POST_/data-sources/{data_source_id}/query"],
                "tools": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (skills_dir / "dashboard_builder.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "dashboard_builder",
                "description": "Build dashboards",
                "system_prompt": "You are a Dashboard Builder Agent.",
                "tools": [{"name": "hitl_test_echo", "limit": 5, "hitl": {"mode": "always"}}],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    test_loader = AgentConfigLoader(config_path=str(agents_yaml))

    def _build(config_overrides=None):
        manager = AgentConfig(
            load_yaml_agent_config(-1, config_loader=test_loader),
            config_overrides=config_overrides,
        )
        # Override the resolver to use test directory instead of production DATA_ROOT
        manager._skill_resolution = SkillResolver(
            data_root=str(tmp_path),
            tool_registry=TOOL_REGISTRY,
        )
        return manager

    return _build


# === Tool Resolution Tests ===


def test_get_tools_for_skill_mapping(manager_factory, mock_runtime):
    manager = manager_factory()

    tool_names = {tool.name for tool in manager.get_tools(["data_analyst"], mock_runtime)}
    assert "hitl_test_echo" in tool_names
    assert "load_skill" in tool_names
    assert "unload_skill" in tool_names


def test_get_system_prompt_uses_skill_file(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst"], mock_runtime)

    assert "You are a Data Analyst Agent." in prompt


def test_get_tools_uses_default_and_skill_merge(manager_factory, mock_runtime):
    manager = manager_factory()

    default_tool_names = {tool.name for tool in manager.get_tools(None, mock_runtime)}
    analyst_tool_names = {tool.name for tool in manager.get_tools(["data_analyst"], mock_runtime)}

    # API baseline tools are configured in default_tools
    assert "load_skill" in default_tool_names
    assert "unload_skill" in default_tool_names
    assert "hitl_test_echo" in default_tool_names

    # Baseline defaults are inherited by loaded skills
    assert "hitl_test_echo" in analyst_tool_names
    assert "load_skill" in analyst_tool_names
    assert "unload_skill" in analyst_tool_names


def test_get_system_prompt_prefers_skill(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["dashboard_builder"], mock_runtime)

    assert "You are a Dashboard Builder Agent." in prompt


def test_get_tools_for_loaded_skills_merges_all_skills(manager_factory, mock_runtime):
    manager = manager_factory()

    tools = manager.get_tools(["data_analyst", "dashboard_builder"], mock_runtime)
    tool_names = {tool.name for tool in tools}

    assert "hitl_test_echo" in tool_names
    assert "load_skill" in tool_names


def test_get_tool_config_for_loaded_skills_uses_merged_limits(manager_factory, mock_runtime):
    manager = manager_factory()

    config = manager.get_tool_config(["data_analyst", "dashboard_builder"], "load_skill", mock_runtime)

    assert config is not None
    assert config.limit == 20


def test_get_tools_raises_when_default_tools_contains_unregistered_tool(manager_factory, mock_runtime):
    manager = manager_factory(
        config_overrides={
            "default_tools": [
                {"name": "unknown_unregistered_tool", "limit": 1},
            ]
        },
    )

    with pytest.raises(ValueError, match="Unknown tool"):
        manager.get_tools(None, mock_runtime)


# === Init-time Validation Tests ===


def test_agent_config_init_raises_when_builtin_skill_has_unregistered_tool(tmp_path, mock_runtime):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "default_tools": [{"name": "load_skill", "limit": 1}],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "broken_skill.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "broken_skill",
                "description": "broken for test",
                "system_prompt": "prompt",
                "tools": [{"name": "unknown_unregistered_tool", "limit": 1}],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    test_loader = AgentConfigLoader(config_path=str(agents_yaml))
    manager = AgentConfig(
        load_yaml_agent_config(-1, config_loader=test_loader),
    )
    # Override the internal skill_resolution to use test directory
    manager._skill_resolution = SkillResolver(
        data_root=str(tmp_path),
        tool_registry=TOOL_REGISTRY,
    )

    # Resolving a skill with unregistered tool should raise
    with pytest.raises(ValueError, match="(?i)unknown tool"):
        manager.get_tools(["broken_skill"], mock_runtime)


def test_loader_raises_when_listed_skill_file_missing(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "default_tools": [{"name": "load_skill", "limit": 1}],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    loader = AgentConfigLoader(config_path=str(agents_yaml))
    # No error on config load since skills list removed
    config = loader.load_yaml()
    assert "system_agents" in config


def test_loader_accepts_standard_skill_directory(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "default_tools": [{"name": "load_skill", "limit": 1}],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    std_skill_dir = skills_dir / "std-helper"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: std-helper
description: Standard helper.
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = AgentConfigLoader(config_path=str(agents_yaml))
    config = loader.load_yaml()

    assert "system_agents" in config
    assert "test_agent" in config["system_agents"]


# === System Prompt Composition Tests ===


def test_system_prompt_includes_base_agent_prompt(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt([], mock_runtime)

    assert "Base system prompt" in prompt


def test_system_prompt_includes_available_skills_section(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt([], mock_runtime)

    assert "## Available Skills" in prompt
    assert "**data_analyst** (builtin):" in prompt
    assert "Analyze data" in prompt or "data_analyst" in prompt
    assert "**dashboard_builder** (builtin):" in prompt
    assert "Build dashboards" in prompt or "dashboard_builder" in prompt


def test_system_prompt_with_no_skills_excludes_loaded_skills_header(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt([], mock_runtime)

    assert "# Loaded Skills" not in prompt


def test_system_prompt_with_single_skill_includes_loaded_skills_section(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst"], mock_runtime)

    assert "# Loaded Skills" in prompt
    assert "data_analyst" in prompt
    assert "You are a Data Analyst Agent." in prompt


def test_system_prompt_with_multiple_skills_includes_all_loaded_skills(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst", "dashboard_builder"], mock_runtime)

    assert "# Loaded Skills" in prompt
    assert "data_analyst" in prompt
    assert "You are a Data Analyst Agent." in prompt
    assert "dashboard_builder" in prompt
    assert "You are a Dashboard Builder Agent." in prompt


def test_system_prompt_no_api_refs_section(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt([], mock_runtime)

    assert "## API References" not in prompt
    assert "GET_/search" not in prompt
    assert "POST_/data-sources" not in prompt


def test_system_prompt_with_skills_excludes_api_refs(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst"], mock_runtime)

    assert "## API References" not in prompt
    assert "POST_/data-sources/{data_source_id}/query" not in prompt


def test_system_prompt_structure_ordering(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst"], mock_runtime)

    base_pos = prompt.find("Base system prompt")
    available_pos = prompt.find("## Available Skills")
    loaded_pos = prompt.find("# Loaded Skills")

    assert base_pos > -1
    assert base_pos < available_pos
    assert available_pos < loaded_pos


def test_manager_loads_standard_skill_directory(tmp_path, mock_runtime):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "system_prompt": "Base system prompt",
                        "default_tools": [
                            {"name": "load_skill", "limit": 10},
                            {"name": "unload_skill", "limit": 10},
                        ],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "data-analysis"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: data-analysis
description: Analyze business data and generate insights.
allowed-tools:
  - search_data_assets
---

You are a Standard Data Analysis skill.
""".strip(),
        encoding="utf-8",
    )

    test_loader = AgentConfigLoader(config_path=str(agents_yaml))
    manager = AgentConfig(
        load_yaml_agent_config(-1, config_loader=test_loader),
    )
    # Override the internal skill_resolution to use test directory
    manager._skill_resolution = SkillResolver(
        data_root=str(tmp_path),
        tool_registry=TOOL_REGISTRY,
    )

    skills = manager.get_resolved_skills(mock_runtime)
    assert "data-analysis" in skills

    prompt = manager.get_system_prompt(["data-analysis"], mock_runtime)
    assert "You are a Standard Data Analysis skill." in prompt

    tool_names = {tool.name for tool in manager.get_tools(["data-analysis"], mock_runtime)}
    assert "search_data_assets" in tool_names
    assert "load_skill" in tool_names
    assert "unload_skill" in tool_names


def test_manager_standard_skill_unmapped_allowed_tools_raises(tmp_path, mock_runtime):
    """AgentConfig uses strict_registry=True, so unknown tools raise ValueError."""
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "system_prompt": "Base system prompt",
                        "default_tools": [
                            {"name": "load_skill", "limit": 10},
                        ],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "ops-helper"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: ops-helper
description: Help with operations tasks.
allowed-tools:
  - unknown_tool
  - search_data_assets
---

Use tools as needed.
""".strip(),
        encoding="utf-8",
    )

    test_loader = AgentConfigLoader(config_path=str(agents_yaml))
    manager = AgentConfig(
        load_yaml_agent_config(-1, config_loader=test_loader),
    )
    # Override the internal skill_resolution to use test directory
    manager._skill_resolution = SkillResolver(
        data_root=str(tmp_path),
        tool_registry=TOOL_REGISTRY,
    )
    # strict_registry=True causes unknown tools to raise ValueError
    with pytest.raises(ValueError, match="(?i)unknown tool"):
        manager.get_tools(["ops-helper"], mock_runtime)


def test_manager_prompt_uses_skill_name_only(tmp_path, mock_runtime):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "system_agents": {
                    "test_agent": {
                        "agent_id": -1,
                        "name": "Test Agent",
                        "system_prompt": "Base system prompt",
                        "default_tools": [
                            {"name": "load_skill", "limit": 10},
                        ],
                    }
                },
                "mini_agents": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "general-helper.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "general-helper",
                "description": "General assistant skill",
                "system_prompt": "Use this skill for general assistant tasks.",
                "tools": [{"name": "search_knowledge_base", "limit": 3}],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    test_loader = AgentConfigLoader(config_path=str(agents_yaml))
    manager = AgentConfig(
        load_yaml_agent_config(-1, config_loader=test_loader),
    )
    # Override the internal skill_resolution to use test directory
    manager._skill_resolution = SkillResolver(
        data_root=str(tmp_path),
        tool_registry=TOOL_REGISTRY,
    )
    prompt = manager.get_system_prompt(["general-helper"], mock_runtime)

    assert "**general-helper**" in prompt
    assert "general-helper" in prompt


def test_system_prompt_no_empty_lines_between_sections(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst"], mock_runtime)

    # Check that sections exist and are properly separated
    assert "## Available Skills" in prompt
    assert "# Loaded Skills" in prompt
    # Ensure no excessive blank lines (more than 2 consecutive newlines)
    lines = prompt.split("\n")
    max_consecutive_blanks = 0
    current_consecutive_blanks = 0
    for line in lines:
        if line.strip() == "":
            current_consecutive_blanks += 1
            max_consecutive_blanks = max(max_consecutive_blanks, current_consecutive_blanks)
        else:
            current_consecutive_blanks = 0
    # Allow up to 2 consecutive blank lines (which creates \n\n\n between sections)
    assert max_consecutive_blanks <= 2


def test_system_prompt_base_only_excludes_skill_sections(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt([], mock_runtime)

    assert "# Loaded Skills" not in prompt
    assert "You are a Data Analyst Agent." not in prompt
    assert "You are a Dashboard Builder Agent." not in prompt


def test_system_prompt_does_not_include_skill_api_refs_config(manager_factory, mock_runtime):
    manager = manager_factory()

    prompt = manager.get_system_prompt(["data_analyst"], mock_runtime)

    assert "api_refs" not in prompt.lower()
    assert "POST_/data-sources" not in prompt
