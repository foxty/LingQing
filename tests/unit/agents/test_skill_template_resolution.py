"""Tests for skill resolution in AgentConfig."""

import pytest

from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, AgentTenantContext, AgentUserContext
from apps.tenant_app_service.agents.system_agent_config import load_yaml_agent_config
from apps.tenant_app_service.skills.resolution import SkillResolver, reset_default_skill_resolver


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
def config_manager(mock_runtime, tmp_path):
    """Create AgentConfig with builtin skills copied to test directory."""
    import shutil

    from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY
    from tests.conftest import project_root

    # Copy real builtin skills to test directory so resolver can find them
    src_skills = project_root / "config" / "skills"
    dst_skills = tmp_path / "skills"
    if src_skills.exists():
        shutil.copytree(src_skills, dst_skills)

    # Reset and create a test resolver pointing to tmp_path
    reset_default_skill_resolver()
    test_resolver = SkillResolver(data_root=str(tmp_path), tool_registry=TOOL_REGISTRY)

    manager = AgentConfig(load_yaml_agent_config(-1))
    manager._skill_resolution = test_resolver
    return manager


class TestSkillTemplateResolution:
    """Test skill resolution behavior."""

    def test_skills_are_loaded_from_resolution(self, config_manager, mock_runtime):
        skills = config_manager.get_resolved_skills(mock_runtime)

        assert "data-analyst" in skills
        assert "dashboard-builder" in skills
        assert "task-scheduler" in skills
        assert "report-writer" in skills

    def test_skill_meta_comes_from_skill_descriptions(self, config_manager, mock_runtime):
        skills_meta = config_manager.get_resolved_skills_meta(mock_runtime)
        names = {entry["name"] for entry in skills_meta}

        assert "data-analyst" in names
        assert "dashboard-builder" in names

    def test_system_prompt_for_skill_comes_from_skill_file(self, config_manager, mock_runtime):
        prompt = config_manager.get_system_prompt(["data-analyst"], mock_runtime)

        assert "You operate as a **data analyst**" in prompt
        assert "## Responsibilities" in prompt

    def test_unknown_skill_raises_error(self, config_manager, mock_runtime):
        with pytest.raises(ValueError, match="Skill 'unknown' not found"):
            config_manager.normalize_loaded_skills(["unknown"], mock_runtime)

    def test_base_mode_tools_come_from_default_tools(self, config_manager, mock_runtime):
        tools = config_manager.get_tools([], mock_runtime)
        tool_names = {tool.name for tool in tools}

        assert "load_skill" in tool_names
        assert "create_report" not in tool_names
        assert "schedule_task" not in tool_names

    def test_loaded_scheduler_skill_exposes_scheduler_tools(self, config_manager, mock_runtime):
        tools = config_manager.get_tools(["task-scheduler"], mock_runtime)
        tool_names = {tool.name for tool in tools}
        assert "schedule_task" in tool_names
        assert "list_scheduled_tasks" in tool_names
