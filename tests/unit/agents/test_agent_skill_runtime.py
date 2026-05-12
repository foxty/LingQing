"""Tests for runtime skill resolution in AgentConfig."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.domain import (
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
    SkillScope,
)
from apps.tenant_app_service.skills.resolution import SkillResolver


@pytest.fixture
def empty_tool_registry():
    return {}


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


class TestConfigManagerSkillResolution:
    """Test skill resolution through AgentConfig."""

    def _create_skill_yaml(self, path: Path, name: str, prompt: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"name: {name}\nsystem_prompt: {prompt}\n", encoding="utf-8")

    def _make_config_manager(self, skill_resolution):
        """Create AgentConfig with mocked config loader."""
        manager = AgentConfig(
            {
                "agent_id": -1,
                "name": "TestAgent",
                "system_prompt": "You are a test agent.",
                "default_tools": [],
            }
        )
        manager._skill_resolution = skill_resolution
        return manager

    def test_get_resolved_skills_returns_all_scopes(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin")

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            resolved = config.get_resolved_skills(mock_runtime)

            assert "data_analyst" in resolved
            assert resolved["data_analyst"].scope == SkillScope.BUILTIN

    def test_get_resolved_skills_empty_without_runtime(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            # Create a minimal runtime context
            runtime = AgentRuntimeContext(
                tenant=AgentTenantContext(tenant_id=1, tenant_name="Test", config={}),
                user=AgentUserContext(
                    user_id=1,
                    username="test",
                    role="user",
                    tenant_id=1,
                    tenant_name="Test",
                ),
                agent_id=-1,
                agent_name="TestAgent",
                thread_id="t1",
                session_id="s1",
            )
            resolved = config.get_resolved_skills(runtime)

            assert resolved == {}

    def test_validate_load_skill_returns_config(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin")

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            skill = config.validate_load_skill("data_analyst", mock_runtime)

            assert skill is not None
            assert skill.name == "data_analyst"

    def test_validate_load_skill_returns_none_for_unknown(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir()

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            skill = config.validate_load_skill("unknown", mock_runtime)

            assert skill is None

    def test_normalize_loaded_skills_validates(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin")

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)

            normalized = config.normalize_loaded_skills(["data_analyst"], mock_runtime)
            assert normalized == ["data_analyst"]

            with pytest.raises(ValueError, match="Skill 'unknown' not found"):
                config.normalize_loaded_skills(["unknown"], mock_runtime)

    def test_get_tools_returns_base_tools(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir()

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            tools = config.get_tools([], mock_runtime)

            assert tools == []

    def test_get_system_prompt_includes_available_skills(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin")

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            prompt = config.get_system_prompt([], mock_runtime)

            assert "## Available Skills" in prompt
            assert "(builtin)" in prompt
            assert "data_analyst" in prompt

    def test_get_system_prompt_includes_loaded_skill(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin")

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            prompt = config.get_system_prompt(["data_analyst"], mock_runtime)

            assert "# Loaded Skills" in prompt
            assert "(builtin)" in prompt
            assert "/skills/data_analyst" in prompt


class TestConfigManagerTenantScope:
    """Test runtime resolution with tenant-scoped skills through AgentConfig."""

    def _create_skill_yaml(self, path: Path, name: str, prompt: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"name: {name}\nsystem_prompt: {prompt}\n", encoding="utf-8")

    def _make_config_manager(self, skill_resolution):
        manager = AgentConfig(
            {
                "agent_id": -1,
                "name": "TestAgent",
                "system_prompt": "You are a test agent.",
                "default_tools": [],
            }
        )
        manager._skill_resolution = skill_resolution
        return manager

    def test_tenant_skill_shows_in_prompt(self, empty_tool_registry, mock_runtime):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            tenant_dir = Path(data_root) / "tenants/tenant_1/skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin")
            self._create_skill_yaml(tenant_dir / "data_analyst.yaml", "data_analyst", "tenant")

            skill_res = SkillResolver(
                data_root=data_root,
                tool_registry=empty_tool_registry,
            )
            config = self._make_config_manager(skill_res)
            prompt = config.get_system_prompt([], mock_runtime)

            # Tenant scope should appear in the prompt
            assert "(tenant)" in prompt
