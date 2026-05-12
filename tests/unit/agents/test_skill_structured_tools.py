"""Test structured tools configuration in SKILL.md frontmatter."""

import pytest

from apps.tenant_app_service.agents.domain import TOOL_LIMIT_UNLIMITED
from apps.tenant_app_service.agents.skills.loader import SkillConfigLoader
from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY

pytestmark = pytest.mark.filterwarnings("ignore:SkillConfigLoader is deprecated:DeprecationWarning")


def test_standard_skill_structured_tools_with_metadata(tmp_path):
    """Test that SKILL.md supports structured tools with limit, cacheable, etc."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "dashboard-builder"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: dashboard-builder
description: Build dashboards with rich tool metadata.
tools:
  - name: create_dashboard
    limit: 5
    cache_invalidates: [get_dashboard_config]
  - name: get_dashboard_config
    limit: 10
    result_retention: long_lived
    cacheable: true
  - name: search_data_assets
    limit: 10
    result_retention: long_lived
    cacheable: true
---

You are a Dashboard Builder Agent.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "dashboard-builder" in skills
    skill = skills["dashboard-builder"]
    assert len(skill.tools) == 3

    # Check create_dashboard
    create_tool = skill.tools[0]
    assert create_tool.name == "create_dashboard"
    assert create_tool.limit == 5
    assert create_tool.cache_invalidates == ["get_dashboard_config"]
    assert create_tool.cacheable is False

    # Check get_dashboard_config
    get_tool = skill.tools[1]
    assert get_tool.name == "get_dashboard_config"
    assert get_tool.limit == 10
    assert get_tool.result_retention == "long_lived"
    assert get_tool.cacheable is True

    # Check search_data_assets
    search_tool = skill.tools[2]
    assert search_tool.name == "search_data_assets"
    assert search_tool.limit == 10
    assert search_tool.result_retention == "long_lived"
    assert search_tool.cacheable is True


def test_standard_skill_backward_compatible_allowed_tools(tmp_path):
    """Test that simple allowed-tools still works for backward compatibility."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "simple-skill"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: simple-skill
description: Simple skill with basic allowed-tools.
allowed-tools: search_data_assets search_documents
---

Simple body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "simple-skill" in skills
    skill = skills["simple-skill"]
    assert len(skill.tools) == 2
    assert skill.tools[0].name == "search_data_assets"
    assert skill.tools[0].limit == TOOL_LIMIT_UNLIMITED
    assert skill.tools[1].name == "search_documents"


def test_standard_skill_tools_takes_precedence_over_allowed_tools(tmp_path):
    """Test that tools field takes precedence when both are present."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "mixed-skill"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: mixed-skill
description: Has both tools and allowed-tools.
allowed-tools: search_data_assets
tools:
  - name: search_documents
    limit: 5
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "mixed-skill" in skills
    skill = skills["mixed-skill"]
    # Should use tools, not allowed-tools
    assert len(skill.tools) == 1
    assert skill.tools[0].name == "search_documents"
    assert skill.tools[0].limit == 5


def test_standard_skill_structured_tools_validation_errors(tmp_path):
    """Test validation errors for invalid structured tools."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "invalid-skill"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: invalid-skill
description: Invalid tools config.
tools:
  - name: search_data_assets
    limit: -5
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="field 'limit' must be integer >= 0"):
        loader.load_all()


def test_standard_skill_structured_tools_duplicate_warning(tmp_path, caplog):
    """Test that duplicate tools log a warning."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "duplicate-skill"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: duplicate-skill
description: Has duplicate tools.
tools:
  - name: search_data_assets
    limit: 5
  - name: search_data_assets
    limit: 10
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["duplicate-skill"]
    assert len(skill.tools) == 1
    assert skill.tools[0].limit == 5  # First occurrence wins
    assert "has duplicate tool 'search_data_assets'" in caplog.text


def test_standard_skill_structured_tools_with_hitl_config(tmp_path):
    """Test structured tools with hitl configuration."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "hitl-skill"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: hitl-skill
description: Skill with HITL configuration.
tools:
  - name: create_dashboard
    limit: 5
    hitl:
      mode: always
  - name: search_data_assets
    limit: 10
    hitl:
      mode: never
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["hitl-skill"]
    assert len(skill.tools) == 2
    assert skill.tools[0].hitl == {"mode": "always"}
    assert skill.tools[1].hitl == {"mode": "never"}


def test_standard_skill_structured_tools_invalid_result_retention(tmp_path):
    """Test validation error for invalid result_retention value."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "invalid-retention"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: invalid-retention
description: Invalid result retention.
tools:
  - name: search_data_assets
    result_retention: invalid_value
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="field 'result_retention'"):
        loader.load_all()


def test_standard_skill_structured_tools_invalid_cacheable_type(tmp_path):
    """Test validation error for non-boolean cacheable."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "invalid-cacheable"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: invalid-cacheable
description: Invalid cacheable type.
tools:
  - name: search_data_assets
    cacheable: "yes"
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="field 'cacheable' must be boolean"):
        loader.load_all()


def test_standard_skill_structured_tools_invalid_cache_invalidates(tmp_path):
    """Test validation error for invalid cache_invalidates format."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "invalid-invalidate"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: invalid-invalidate
description: Invalid cache_invalidates.
tools:
  - name: create_dashboard
    cache_invalidates: not_a_list
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="field 'cache_invalidates'"):
        loader.load_all()


def test_standard_skill_structured_tools_invalid_hitl_type(tmp_path):
    """Test validation error for non-dict hitl."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "invalid-hitl"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: invalid-hitl
description: Invalid hitl type.
tools:
  - name: create_dashboard
    hitl: "always"
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="field 'hitl' must be an object"):
        loader.load_all()


def test_standard_skill_structured_tools_empty_list(tmp_path):
    """Test skill with empty tools list."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "empty-tools"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: empty-tools
description: Skill with no tools.
tools: []
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["empty-tools"]
    assert len(skill.tools) == 0


def test_standard_skill_structured_tools_minimal_config(tmp_path):
    """Test tool with only name (all defaults)."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "minimal-tool"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: minimal-tool
description: Minimal tool config.
tools:
  - name: search_data_assets
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["minimal-tool"]
    assert len(skill.tools) == 1
    assert skill.tools[0].name == "search_data_assets"
    assert skill.tools[0].limit == TOOL_LIMIT_UNLIMITED
    assert skill.tools[0].cacheable is False
    assert skill.tools[0].result_retention == "transient"
    assert skill.tools[0].cache_invalidates == []
    assert skill.tools[0].hitl == {}


def test_standard_skill_structured_tools_invalid_cache_invalidates_items(tmp_path):
    """Test validation error for cache_invalidates with non-string items."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "invalid-items"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: invalid-items
description: Invalid cache_invalidates items.
tools:
  - name: create_dashboard
    cache_invalidates: [get_dashboard_config, 123]
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="field 'cache_invalidates'"):
        loader.load_all()


def test_standard_skill_structured_tools_multiple_cache_invalidates(tmp_path):
    """Test tool with multiple cache invalidations."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "multi-invalidate"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: multi-invalidate
description: Multiple cache invalidations.
tools:
  - name: create_dashboard
    cache_invalidates:
      - get_dashboard_config
      - validate_widget_query
      - search_data_assets
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["multi-invalidate"]
    assert len(skill.tools) == 1
    assert len(skill.tools[0].cache_invalidates) == 3
    assert "get_dashboard_config" in skill.tools[0].cache_invalidates
    assert "validate_widget_query" in skill.tools[0].cache_invalidates
    assert "search_data_assets" in skill.tools[0].cache_invalidates


def test_standard_skill_structured_tools_unmapped_tool_skipped(tmp_path, caplog):
    """Test that unmapped tools are skipped with warning."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "unmapped-tool"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: unmapped-tool
description: Has unmapped tool.
tools:
  - name: search_data_assets
    limit: 5
  - name: nonexistent_tool
    limit: 10
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["unmapped-tool"]
    assert len(skill.tools) == 1  # Only valid tool
    assert skill.tools[0].name == "search_data_assets"
    assert "references unmapped tool 'nonexistent_tool'; skipping" in caplog.text


def test_standard_skill_structured_tools_complex_hitl_config(tmp_path):
    """Test complex hitl configuration with multiple fields."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "complex-hitl"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: complex-hitl
description: Complex HITL config.
tools:
  - name: create_dashboard
    hitl:
      mode: conditional
      threshold: high_risk
      require_comment: true
---

Body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["complex-hitl"]
    assert skill.tools[0].hitl == {
        "mode": "conditional",
        "threshold": "high_risk",
        "require_comment": True,
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
