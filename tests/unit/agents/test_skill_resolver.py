import pytest

from apps.tenant_app_service.agents.skills.resolver import resolve_effective_skill_tools


def test_merge_default_and_skill_tools_preserves_order_and_additions():
    default_tools = [
        {"name": "load_skill", "limit": 2},
        {"name": "search_knowledge_base", "limit": 5},
    ]
    skill_tools = [
        {"name": "list_data_sources", "limit": 2},
        {"name": "search_data_assets", "limit": 5},
    ]

    merged = resolve_effective_skill_tools(default_tools=default_tools, skill_tools=skill_tools)

    assert [t.name for t in merged] == [
        "load_skill",
        "search_knowledge_base",
        "list_data_sources",
        "search_data_assets",
    ]


def test_duplicate_tool_uses_stricter_limit():
    default_tools = [{"name": "search_knowledge_base", "limit": 5}]
    skill_tools = [{"name": "search_knowledge_base", "limit": 2}]

    merged = resolve_effective_skill_tools(default_tools=default_tools, skill_tools=skill_tools)

    assert len(merged) == 1
    assert merged[0].name == "search_knowledge_base"
    assert merged[0].limit == 2


def test_duplicate_tool_unlimited_and_finite_prefers_finite():
    default_tools = [{"name": "search_knowledge_base", "limit": 0}]
    skill_tools = [{"name": "search_knowledge_base", "limit": 3}]

    merged = resolve_effective_skill_tools(default_tools=default_tools, skill_tools=skill_tools)

    assert len(merged) == 1
    assert merged[0].limit == 3


def test_unknown_tools_skipped_when_registry_not_strict():
    default_tools = [{"name": "load_skill", "limit": 1}]
    skill_tools = [{"name": "unknown_tool", "limit": 1}]

    merged = resolve_effective_skill_tools(
        default_tools=default_tools,
        skill_tools=skill_tools,
        tool_registry={"load_skill": object()},
        strict_registry=False,
    )

    assert [t.name for t in merged] == ["load_skill"]


def test_unknown_tools_raise_when_registry_strict():
    with pytest.raises(ValueError, match="Unknown tool"):
        resolve_effective_skill_tools(
            default_tools=[{"name": "load_skill", "limit": 1}],
            skill_tools=[{"name": "unknown_tool", "limit": 1}],
            tool_registry={"load_skill": object()},
            strict_registry=True,
        )
