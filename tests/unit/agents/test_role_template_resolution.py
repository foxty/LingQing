"""Tests for skill resolution in AgentConfig."""

import shutil

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
def manager_with_skills(mock_runtime, tmp_path):
    """Create AgentConfig with builtin skills copied to test directory."""
    from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY
    from tests.conftest import project_root

    # Copy real builtin skills to test directory
    src_skills = project_root / "config" / "skills"
    dst_skills = tmp_path / "skills"
    if src_skills.exists():
        shutil.copytree(src_skills, dst_skills)

    # Create test resolver
    reset_default_skill_resolver()
    test_resolver = SkillResolver(data_root=str(tmp_path), tool_registry=TOOL_REGISTRY)

    manager = AgentConfig(load_yaml_agent_config(-1))
    manager._skill_resolution = test_resolver
    return manager


class TestSkillTemplateResolution:
    """Test skill resolution behavior."""

    def test_skills_are_loaded_from_resolution(self, manager_with_skills, mock_runtime):
        skills = manager_with_skills.get_resolved_skills(mock_runtime)

        assert "data_analyst" in skills
        assert "dashboard_builder" in skills

    def test_skill_meta_comes_from_skill_descriptions(self, manager_with_skills, mock_runtime):
        skills_meta = manager_with_skills.get_resolved_skills_meta(mock_runtime)
        names = {entry["name"] for entry in skills_meta}

        assert "data_analyst" in names
        assert "dashboard_builder" in names

    def test_system_prompt_for_skill_comes_from_skill_file(self, manager_with_skills, mock_runtime):
        prompt = manager_with_skills.get_system_prompt(["data_analyst"], mock_runtime)

        assert "You are a Data Analyst Agent." in prompt

    def test_unknown_skill_raises_error(self, manager_with_skills, mock_runtime):
        with pytest.raises(ValueError, match="Skill 'unknown' not found"):
            manager_with_skills.normalize_loaded_skills(["unknown"], mock_runtime)

    def test_base_mode_tools_come_from_default_tools(self, manager_with_skills, mock_runtime):
        tools = manager_with_skills.get_tools([], mock_runtime)
        tool_names = {tool.name for tool in tools}

        assert {"hitl_test_echo", "load_skill"}.issubset(tool_names)
