import pytest

from apps.tenant_app_service.agents.skills.loader import SkillConfigLoader
from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY


pytestmark = pytest.mark.filterwarnings("ignore:SkillConfigLoader is deprecated:DeprecationWarning")


def test_load_valid_skill_file(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "data_analyst.yaml").write_text(
        """
name: data_analyst
description: Data analysis skill
system_prompt: You are a data analyst.
tools:
  - name: list_data_sources
    limit: 2
  - name: search_data_assets
    limit: 5
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir))
    skills = loader.load_all()

    assert "data_analyst" in skills
    skill = skills["data_analyst"]
    assert skill.name == "data_analyst"
    assert skill.system_prompt == "You are a data analyst."
    assert len(skill.tools) == 2
    assert skill.tools[0].name == "list_data_sources"
    assert skill.tools[0].limit == 2


def test_duplicate_skill_name_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "a.yaml").write_text(
        """
name: same_name
system_prompt: prompt a
tools: []
""".strip(),
        encoding="utf-8",
    )
    (skills_dir / "b.yaml").write_text(
        """
name: same_name
system_prompt: prompt b
tools: []
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir))
    with pytest.raises(ValueError, match="Duplicate skill name"):
        loader.load_all()


def test_missing_required_name_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "bad.yaml").write_text(
        """
description: missing name
system_prompt: prompt
tools: []
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir))
    with pytest.raises(ValueError, match="field 'name'"):
        loader.load_all()


def test_unknown_tool_rejected_with_registry(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "bad_tool.yaml").write_text(
        """
name: test
system_prompt: prompt
tools:
  - name: unknown_tool
    limit: 1
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(
        skills_dir=str(skills_dir),
        tool_registry={"search_documents": object()},
    )
    with pytest.raises(ValueError, match="unknown tool"):
        loader.load_all()


def test_invalid_tool_limit_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "bad_limit.yaml").write_text(
        """
name: test
system_prompt: prompt
tools:
  - name: search_documents
    limit: -1
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir))
    with pytest.raises(ValueError, match="integer >= 0"):
        loader.load_all()


def test_project_skill_files_load_with_tool_registry():
    loader = SkillConfigLoader(skills_dir="config/skills", tool_registry=TOOL_REGISTRY)
    skills = loader.load_all(force_reload=True)

    assert "data_analyst" in skills
    assert "dashboard_builder" in skills
    assert "app-builder" in skills
    assert "weather-ip-helper" in skills
    assert "default" not in skills


def test_skill_loader_parses_api_refs_fields(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "api_skill.yaml").write_text(
        """
name: api_skill
description: API aware skill
system_prompt: Use APIs.
api_refs:
  - listDataSources
  - createDashboard
tools:
  - name: load_api_spec
    limit: 3
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "api_skill" in skills
    skill = skills["api_skill"]
    assert skill.api_refs == ["listDataSources", "createDashboard"]


def test_load_standard_skill_directory(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "data-analysis"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: data-analysis
description: Analyze business data and generate insights.
scripts:
    - fetch_data.py
metadata:
  author: platform-team
allowed-tools: list_data_sources run_sql_query_on_datasource
---

You are a focused data analysis skill.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "data-analysis" in skills
    skill = skills["data-analysis"]
    assert skill.name == "data-analysis"
    assert skill.source_format == "standard_skill"
    assert skill.skill_metadata == {"author": "platform-team"}
    assert "focused data analysis" in skill.system_prompt
    assert [tool.name for tool in skill.tools] == ["list_data_sources", "run_sql_query_on_datasource"]


def test_standard_skill_unmapped_allowed_tools_are_logged_and_skipped(tmp_path, caplog):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "ops-helper"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: ops-helper
description: Help with operations tasks.
allowed-tools: list_data_sources unknown_tool run_sql_query_on_datasource
---

Use tools as needed.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    skill = skills["ops-helper"]
    assert [tool.name for tool in skill.tools] == ["list_data_sources", "run_sql_query_on_datasource"]
    assert "references unmapped allowed-tool 'unknown_tool'; skipping" in caplog.text


def test_standard_skill_name_must_match_directory(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "data-analysis"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: other-name
description: Analyze data.
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="must match its parent directory name"):
        loader.load_all()


def test_duplicate_skill_name_across_yaml_and_standard_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    (skills_dir / "data-analyst.yaml").write_text(
        """
name: data-analyst
system_prompt: Legacy data analyst.
tools: []
""".strip(),
        encoding="utf-8",
    )

    std_skill_dir = skills_dir / "data-analyst"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: data-analyst
description: Standard data analyst.
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="Duplicate skill name"):
        loader.load_all()


def test_standard_skill_allowed_tools_list_format(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "ops-list"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: ops-list
description: Operations helper with list style tools.
allowed-tools:
  - search_data_assets
  - search_documents
---

Use tools from list format.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "ops-list" in skills
    tool_names = [tool.name for tool in skills["ops-list"].tools]
    assert tool_names == ["search_data_assets", "search_documents"]


def test_standard_skill_allowed_tools_comma_separated_format(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "ops-comma"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: ops-comma
description: Operations helper with comma-separated tools.
allowed-tools: search_data_assets, search_documents,search_data_assets
---

Use tools from comma format.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "ops-comma" in skills
    tool_names = [tool.name for tool in skills["ops-comma"].tools]
    assert tool_names == ["search_data_assets", "search_documents"]


def test_standard_skill_parses_with_bom_and_leading_blank_lines(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "bom-helper"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        "\ufeff\n\n---\nname: bom-helper\ndescription: Parses with BOM and blank lines.\nallowed-tools: search_documents\n---\n\nBody from BOM skill.\n",
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "bom-helper" in skills
    assert skills["bom-helper"].system_prompt == "Body from BOM skill."


def test_standard_skill_unknown_frontmatter_field_logs_warning(tmp_path, caplog):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "unknown-field"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: unknown-field
description: Includes unknown field.
allowed-tools: search_documents
not-a-real-field: value
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "unknown-field" in skills
    assert "contains unknown frontmatter field 'not-a-real-field'; ignoring" in caplog.text


def test_standard_skill_scripts_and_references_not_injected_into_prompt(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "safe-helper"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: safe-helper
description: Helper with extra files.
allowed-tools: search_documents
---

Prompt body only.
""".strip(),
        encoding="utf-8",
    )

    scripts_dir = std_skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "helper.sh").write_text("echo SHOULD_NOT_BE_IN_PROMPT", encoding="utf-8")

    refs_dir = std_skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "REFERENCE.md").write_text("SHOULD_NOT_BE_IN_PROMPT", encoding="utf-8")

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skill = loader.load_all()["safe-helper"]

    assert skill.system_prompt == "Prompt body only."
    assert "SHOULD_NOT_BE_IN_PROMPT" not in skill.system_prompt


def test_legacy_and_standard_core_fields_equivalent(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    (skills_dir / "equiv-one.yaml").write_text(
        """
name: equiv-one
description: Equivalent skill
system_prompt: Equivalent prompt body.
tools:
  - name: search_data_assets
  - name: search_documents
""".strip(),
        encoding="utf-8",
    )

    std_skill_dir = skills_dir / "equiv-two"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: equiv-two
description: Equivalent skill
allowed-tools: search_data_assets search_documents
---

Equivalent prompt body.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    legacy = skills["equiv-one"]
    standard = skills["equiv-two"]

    assert legacy.description == standard.description
    assert legacy.system_prompt == standard.system_prompt
    assert [tool.name for tool in legacy.tools] == [tool.name for tool in standard.tools]


def test_standard_skill_missing_frontmatter_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "no-frontmatter"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        "This file does not start with frontmatter.",
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="must start with frontmatter delimiter"):
        loader.load_all()


def test_standard_skill_invalid_frontmatter_yaml_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "bad-yaml"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: bad-yaml
description: invalid
metadata: [oops
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="Invalid frontmatter YAML"):
        loader.load_all()


def test_standard_skill_frontmatter_must_be_object(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "frontmatter-list"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
- not
- an
- object
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="must be a YAML object"):
        loader.load_all()


def test_standard_skill_empty_body_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "empty-body"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: empty-body
description: Has no body.
---

""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="must include non-empty markdown body"):
        loader.load_all()


def test_standard_skill_description_too_long_raises_error(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "desc-too-long"
    std_skill_dir.mkdir()
    description = "x" * 1025
    (std_skill_dir / "SKILL.md").write_text(
        f"""
---
name: desc-too-long
description: {description}
---

Body
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    with pytest.raises(ValueError, match="description' must be <= 1024 chars"):
        loader.load_all()


@pytest.mark.parametrize("format_kind", ["legacy", "standard"])
def test_shared_semantic_contract_for_legacy_and_standard_skills(tmp_path, format_kind):
    """Shared semantic contract: both formats should behave equivalently after loading."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    if format_kind == "legacy":
        (skills_dir / "shared-contract.yaml").write_text(
            """
name: shared-contract
description: Shared semantic contract skill.
system_prompt: Shared prompt body.
tools:
  - name: search_data_assets
  - name: search_documents
""".strip(),
            encoding="utf-8",
        )
    else:
        std_skill_dir = skills_dir / "shared-contract"
        std_skill_dir.mkdir()
        (std_skill_dir / "SKILL.md").write_text(
            """
---
name: shared-contract
description: Shared semantic contract skill.
allowed-tools: search_data_assets search_documents
---

Shared prompt body.
""".strip(),
            encoding="utf-8",
        )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "shared-contract" in skills
    skill = skills["shared-contract"]

    assert skill.name == "shared-contract"
    assert skill.description == "Shared semantic contract skill."
    assert skill.system_prompt == "Shared prompt body."
    assert [tool.name for tool in skill.tools] == ["search_data_assets", "search_documents"]


def test_legacy_skill_ignores_display_name_fields(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "general-helper.yaml").write_text(
        """
name: general-helper
display_name: General Helper
description: General helper skill.
system_prompt: Help with general tasks.
tools:
  - name: search_documents
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "general-helper" in skills
    skill = skills["general-helper"]
    assert skill.name == "general-helper"
    assert skill.description == "General helper skill."


def test_legacy_skill_ignores_display_name_kebab_case(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "dashboard-builder.yaml").write_text(
        """
name: dashboard-builder
display-name: Dashboard Builder
description: Dashboard skill.
system_prompt: Build dashboards.
tools:
  - name: search_data_assets
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "dashboard-builder" in skills
    assert skills["dashboard-builder"].name == "dashboard-builder"
    assert skills["dashboard-builder"].description == "Dashboard skill."


def test_standard_skill_ignores_display_name_frontmatter(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "general-helper"
    std_skill_dir.mkdir()
    (std_skill_dir / "SKILL.md").write_text(
        """
---
name: general-helper
display-name: General Helper
description: General helper skill.
allowed-tools: search_documents
---

Help with general tasks.
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    skills = loader.load_all()

    assert "general-helper" in skills
    skill = skills["general-helper"]
    assert skill.name == "general-helper"
    assert skill.description == "General helper skill."


def test_loader_auto_invalidates_cache_when_legacy_yaml_changes(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    file_path = skills_dir / "cache-check.yaml"
    file_path.write_text(
        """
name: cache-check
description: Cache check
system_prompt: v1
tools: []
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    first = loader.load_all()
    assert first["cache-check"].system_prompt == "v1"

    file_path.write_text(
        """
name: cache-check
description: Cache check
system_prompt: v2
tools: []
""".strip(),
        encoding="utf-8",
    )

    second = loader.load_all()
    assert second["cache-check"].system_prompt == "v2"


def test_loader_auto_invalidates_cache_when_standard_skill_changes(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    std_skill_dir = skills_dir / "cache-standard"
    std_skill_dir.mkdir()
    skill_file = std_skill_dir / "SKILL.md"
    skill_file.write_text(
        """
---
name: cache-standard
description: Cache standard
allowed-tools: search_documents
---

prompt v1
""".strip(),
        encoding="utf-8",
    )

    loader = SkillConfigLoader(skills_dir=str(skills_dir), tool_registry=TOOL_REGISTRY)
    first = loader.load_all()
    assert first["cache-standard"].system_prompt == "prompt v1"

    skill_file.write_text(
        """
---
name: cache-standard
description: Cache standard
allowed-tools: search_documents
---

prompt v2
""".strip(),
        encoding="utf-8",
    )

    second = loader.load_all()
    assert second["cache-standard"].system_prompt == "prompt v2"
