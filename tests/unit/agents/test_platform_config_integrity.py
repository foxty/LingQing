"""Validate production agents.yaml platform section against the tool registry."""

from pathlib import Path

from apps.tenant_app_service.agents.platform_tools import (
    build_platform_tool_specs,
    validate_platform_tool_specs,
)
from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY, AgentConfigLoader


def test_production_agents_yaml_platform_tool_specs():
    config_path = Path(__file__).resolve().parents[3] / "config" / "agents.yaml"
    loader = AgentConfigLoader(config_path=str(config_path))
    yaml_config = loader.load_yaml()
    platform = yaml_config.get("platform") or {}
    raw_specs = platform.get("tool_specs") or {}
    merged = build_platform_tool_specs(raw_specs, TOOL_REGISTRY)
    validate_platform_tool_specs(merged, TOOL_REGISTRY, strict_full_catalog=True)
    baseline = platform.get("system_prompt_baseline", "").strip()
    assert baseline
    assert "## Workspace" in baseline
    assert "## Skills" in baseline


def test_load_agent_one_materializes_tool_limits():
    loader = AgentConfigLoader()
    config = loader.materialize_system_agent_document(loader.get_system_agent_config(-1) or {})
    by_name = {item["name"]: item for item in config.get("default_tools", [])}
    assert by_name["search_documents"]["limit"] == 5
    assert by_name["run_bash_script"]["limit"] == 20
