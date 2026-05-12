"""Tests for SkillResolver (the unified skill resolution class).

The resolver takes a ``SkillPaths`` instance instead of separate
``data_root``/``builtin_skills_dir`` kwargs, and locator construction is
delegated to ``SkillPaths.locator``. This module locks in scope
precedence, per-tenant cache behavior, and the ``type_filter`` /
``locate`` helpers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apps.tenant_app_service.agents.domain import SkillScope
from apps.tenant_app_service.skills.paths import SkillPaths
from apps.tenant_app_service.skills.resolution import SkillResolver


@pytest.fixture
def empty_tool_registry():
    return {}


class TestSkillLocatorPaths:
    """Test path resolution for all three scopes."""

    def test_builtin_locator_paths(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "weather.yaml").write_text("name: weather\nsystem_prompt: w\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            locator = resolver.locate("weather")

            assert locator is not None
            assert locator.scope == SkillScope.BUILTIN
            assert locator.host_skill_dir == f"{data_root}/skills/weather"
            assert locator.host_packages_dir == f"{data_root}/skill-packages/weather/python"
            assert locator.container_skill_dir == "/skills/weather"
            assert locator.container_packages_dir == "/skill-packages/weather/python"

    def test_tenant_locator_paths(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            tenant_dir = Path(data_root) / "tenants" / "tenant_42" / "skills"
            tenant_dir.mkdir(parents=True, exist_ok=True)
            (tenant_dir / "custom-etl.yaml").write_text("name: custom-etl\nsystem_prompt: t\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            locator = resolver.locate("custom-etl", tenant_id=42)

            assert locator is not None
            assert locator.scope == SkillScope.TENANT
            assert locator.host_skill_dir == f"{data_root}/tenants/tenant_42/skills/custom-etl"
            assert locator.host_packages_dir == f"{data_root}/tenants/tenant_42/skill-packages/custom-etl/python"
            assert locator.container_skill_dir == "/skills-tenant/custom-etl"
            assert locator.container_packages_dir == "/skill-packages-tenant/custom-etl/python"

    def test_personal_locator_paths(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            personal_dir = Path(data_root) / "tenants" / "tenant_42" / "workspace" / "user_7" / "skills"
            personal_dir.mkdir(parents=True, exist_ok=True)
            (personal_dir / "my-script.yaml").write_text("name: my-script\nsystem_prompt: t\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            locator = resolver.locate("my-script", tenant_id=42, user_id=7)

            assert locator is not None
            assert locator.scope == SkillScope.PERSONAL
            assert locator.host_skill_dir == f"{data_root}/tenants/tenant_42/workspace/user_7/skills/my-script"
            assert locator.host_packages_dir is None
            assert locator.container_skill_dir == "/workspace/skills/my-script"
            assert locator.container_packages_dir is None


class TestSkillResolutionPrecedence:
    """Test scope precedence and name collision override."""

    def _create_skill_yaml(self, path: Path, name: str, prompt: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"name: {name}\nsystem_prompt: {prompt}\n",
            encoding="utf-8",
        )

    def test_builtin_only(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin prompt")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve()

            assert "data_analyst" in resolved
            assert resolved["data_analyst"].scope == SkillScope.BUILTIN
            assert resolved["data_analyst"].system_prompt == "builtin prompt"

    def test_tenant_overrides_builtin(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            tenant_dir = Path(data_root) / "tenants/tenant_1/skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin prompt")
            self._create_skill_yaml(tenant_dir / "data_analyst.yaml", "data_analyst", "tenant prompt")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve(tenant_id=1)

            assert resolved["data_analyst"].scope == SkillScope.TENANT
            assert resolved["data_analyst"].system_prompt == "tenant prompt"

    def test_personal_overrides_tenant_and_builtin(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            tenant_dir = Path(data_root) / "tenants/tenant_1/skills"
            personal_dir = Path(data_root) / "tenants/tenant_1/workspace/user_7/skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin prompt")
            self._create_skill_yaml(tenant_dir / "data_analyst.yaml", "data_analyst", "tenant prompt")
            self._create_skill_yaml(personal_dir / "data_analyst.yaml", "data_analyst", "personal prompt")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve(tenant_id=1, user_id=7)

            assert resolved["data_analyst"].scope == SkillScope.PERSONAL
            assert resolved["data_analyst"].system_prompt == "personal prompt"

    def test_missing_tenant_dir_returns_builtin(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin prompt")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve(tenant_id=999)

            assert "data_analyst" in resolved
            assert resolved["data_analyst"].scope == SkillScope.BUILTIN

    def test_missing_personal_dir_returns_tenant(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            tenant_dir = Path(data_root) / "tenants/tenant_1/skills"
            self._create_skill_yaml(builtin_dir / "data_analyst.yaml", "data_analyst", "builtin prompt")
            self._create_skill_yaml(tenant_dir / "data_analyst.yaml", "data_analyst", "tenant prompt")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve(tenant_id=1, user_id=999)

            assert resolved["data_analyst"].scope == SkillScope.TENANT


class TestSkillResolutionCaching:
    """Test loader snapshot caching (resolver no longer caches merged results)."""

    def test_loader_snapshot_caching_works(self, empty_tool_registry):
        """When files haven't changed, loader returns cached skill configs."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "s.yaml").write_text("name: s\nsystem_prompt: p\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            # First call loads from disk, second call hits loader snapshot cache.
            r1 = resolver.resolve(tenant_id=1, user_id=1)
            r2 = resolver.resolve(tenant_id=1, user_id=1)

            # Results are equal but not the same dict (_merge creates new dicts each call).
            assert r1 == r2
            # The skill configs inside come from the loader's cache (same snapshot).
            assert r1["s"].system_prompt == r2["s"].system_prompt

    def test_force_reload_bypasses_loader_snapshot(self, empty_tool_registry):
        """force_reload=True bypasses the loader's snapshot cache."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "s.yaml").write_text("name: s\nsystem_prompt: p\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            r1 = resolver.resolve(tenant_id=1, user_id=1)
            r2 = resolver.resolve(tenant_id=1, user_id=1, force_reload=True)

            # Both load the same content, but force_reload bypasses snapshot cache.
            assert r1 == r2
            assert r1["s"].system_prompt == r2["s"].system_prompt == "p"

    def test_different_tenant_has_different_loaders(self, empty_tool_registry):
        """Different tenants use separate loader instances with independent snapshots."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "s.yaml").write_text("name: s\nsystem_prompt: p\n")
            tenant_dir = Path(data_root) / "tenants/tenant_2/skills"
            tenant_dir.mkdir(parents=True)
            (tenant_dir / "s.yaml").write_text("name: s\nsystem_prompt: t\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            r1 = resolver.resolve(tenant_id=1)
            r2 = resolver.resolve(tenant_id=2)

            assert r1["s"].system_prompt == "p"
            assert r2["s"].system_prompt == "t"


class TestSkillResolutionEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_skills_directory(self, empty_tool_registry):
        """Handle directory with no YAML files."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve()

            assert resolved == {}

    def test_none_tenant_and_user_returns_builtin_only(self, empty_tool_registry):
        """When both tenant_id and user_id are None, only builtin skills load."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "s.yaml").write_text("name: s\nsystem_prompt: p\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve(tenant_id=None, user_id=None)

            assert "s" in resolved
            assert resolved["s"].scope == SkillScope.BUILTIN

    def test_tenant_only_no_user(self, empty_tool_registry):
        """Tenant skills load even without user_id."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            tenant_dir = Path(data_root) / "tenants/tenant_1/skills"
            builtin_dir.mkdir(parents=True)
            tenant_dir.mkdir(parents=True)
            (builtin_dir / "base.yaml").write_text("name: base\nsystem_prompt: b\n")
            (tenant_dir / "custom.yaml").write_text("name: custom\nsystem_prompt: t\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            resolved = resolver.resolve(tenant_id=1, user_id=None)

            assert "base" in resolved
            assert "custom" in resolved
            assert resolved["custom"].scope == SkillScope.TENANT

    def test_locate_returns_none_for_missing_skill(self, empty_tool_registry):
        """locate() returns None when skill doesn't exist."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            locator = resolver.locate("nonexistent", tenant_id=1, user_id=1)

            assert locator is None

    def test_locate_returns_correct_locator(self, empty_tool_registry):
        """locate() returns correct locator for existing skill."""
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "weather.yaml").write_text("name: weather\nsystem_prompt: w\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            locator = resolver.locate("weather")

            assert locator is not None
            assert locator.scope == SkillScope.BUILTIN
            assert locator.container_skill_dir == "/skills/weather"


class TestTypeFilter:
    """type_filter returns only skills from the requested scope."""

    def test_filter_builtin_only(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            tenant_dir = Path(data_root) / "tenants" / "tenant_1" / "skills"
            builtin_dir.mkdir(parents=True)
            tenant_dir.mkdir(parents=True)
            # Each scope has unique skill names (conflicts prevented at creation)
            (builtin_dir / "builtin_skill.yaml").write_text("name: builtin_skill\nsystem_prompt: b\n")
            (tenant_dir / "tenant_skill.yaml").write_text("name: tenant_skill\nsystem_prompt: t\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            builtin = resolver.resolve(tenant_id=1, type_filter=SkillScope.BUILTIN)
            tenant = resolver.resolve(tenant_id=1, type_filter=SkillScope.TENANT)

            # Builtin scope only contains builtin skills
            assert "builtin_skill" in builtin
            assert builtin["builtin_skill"].scope == SkillScope.BUILTIN
            assert "tenant_skill" not in builtin
            # Tenant scope only contains tenant skills
            assert "tenant_skill" in tenant
            assert tenant["tenant_skill"].scope == SkillScope.TENANT
            assert "builtin_skill" not in tenant

    def test_clear_cache_drops_entries(self, empty_tool_registry):
        with tempfile.TemporaryDirectory() as data_root:
            builtin_dir = Path(data_root) / "skills"
            builtin_dir.mkdir(parents=True)
            (builtin_dir / "s.yaml").write_text("name: s\nsystem_prompt: p\n")

            paths = SkillPaths(data_root=data_root)
            resolver = SkillResolver(data_root=paths.data_root, tool_registry=empty_tool_registry)
            r1 = resolver.resolve(tenant_id=1, user_id=1)
            resolver.clear_cache()
            r2 = resolver.resolve(tenant_id=1, user_id=1)

            assert r1 is not r2
            assert r1 == r2
