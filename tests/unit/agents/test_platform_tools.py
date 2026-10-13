"""Tests for platform tool spec merging and resolution."""

import pytest

from apps.tenant_app_service.agents.domain import ToolConfig
from apps.tenant_app_service.agents.platform_tools import (
    build_platform_tool_specs,
    extract_default_tool_names,
    resolve_tool_defs,
    skill_tool_configs_to_agent_tool_yaml,
    validate_platform_tool_specs,
)


def test_build_platform_tool_specs_fills_registry_defaults():
    registry = {"a": object(), "b": object()}
    merged = build_platform_tool_specs({"a": {"limit": 3}}, registry)
    assert merged["a"] == {"limit": 3}
    assert merged["b"] == {}


def test_build_platform_tool_specs_rejects_unknown():
    with pytest.raises(ValueError, match="unknown tools"):
        build_platform_tool_specs({"missing": {}}, {"a": object()})


def test_validate_platform_tool_specs_strict():
    registry = {"a": object(), "b": object()}
    specs = {"a": {}, "b": {}}
    validate_platform_tool_specs(specs, registry, strict_full_catalog=True)


def test_resolve_tool_defs_applies_platform_policy():
    specs = {"search_documents": {"limit": 5, "cacheable": True}}
    defs = resolve_tool_defs(["search_documents"], specs)
    assert defs == [{"name": "search_documents", "limit": 5, "cacheable": True}]


def test_skill_tool_configs_apply_platform_defaults():
    specs = {"hitl_test_echo": {"limit": 3, "hitl": {"mode": "always"}}}
    skill_tools = [ToolConfig(name="hitl_test_echo", limit=10, hitl={"mode": "never"})]
    defs = skill_tool_configs_to_agent_tool_yaml(skill_tools, specs)
    assert defs[0]["name"] == "hitl_test_echo"
    assert defs[0]["limit"] == 10
    assert defs[0]["hitl"] == {"mode": "never"}


def test_extract_default_tool_names_supports_strings_and_dicts():
    names = extract_default_tool_names(
        [
            "load_skill",
            {"name": "search_documents", "limit": 99},
            "load_skill",
        ]
    )
    assert names == ["load_skill", "search_documents"]
