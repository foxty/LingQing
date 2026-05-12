"""Tests for apps.tenant_app_service.skills.paths.

Locks in the on-disk layout strings. Any drift here will break the
sandbox bind-mount contract. The locator output is compared against
hardcoded expected strings that mirror the historical bind-mount
layout, so the bind-mount contract is preserved.
"""

from __future__ import annotations

from apps.tenant_app_service.skills.domain import SkillType
from apps.tenant_app_service.skills.paths import (
    CONTAINER_BUILTIN_DIR,
    CONTAINER_BUILTIN_PACKAGES_DIR,
    CONTAINER_PERSONAL_DIR,
    CONTAINER_TENANT_DIR,
    CONTAINER_TENANT_PACKAGES_DIR,
    SkillPaths,
)


def test_container_constants_match_legacy_bind_mounts() -> None:
    assert CONTAINER_BUILTIN_DIR == "/skills"
    assert CONTAINER_TENANT_DIR == "/skills-tenant"
    assert CONTAINER_BUILTIN_PACKAGES_DIR == "/skill-packages"
    assert CONTAINER_TENANT_PACKAGES_DIR == "/skill-packages-tenant"
    assert CONTAINER_PERSONAL_DIR == "/workspace/skills"


def test_builtin_paths() -> None:
    p = SkillPaths(data_root="/data")
    assert p.builtin_dir == "/data/skills"
    assert p.builtin_packages_dir("demo") == "/data/skill-packages/demo/python"


def test_tenant_paths() -> None:
    p = SkillPaths(data_root="/data")
    assert p.tenant_skills_dir(7) == "/data/tenants/tenant_7/skills"
    assert p.tenant_packages_dir(7) == "/data/tenants/tenant_7/skill-packages"
    assert p.tenant_skill_dir(7, "demo") == "/data/tenants/tenant_7/skills/demo"


def test_personal_paths() -> None:
    p = SkillPaths(data_root="/data")
    assert p.personal_skills_dir(7, 9) == "/data/tenants/tenant_7/workspace/user_9/skills"
    assert p.personal_skill_dir(7, 9, "demo") == ("/data/tenants/tenant_7/workspace/user_9/skills/demo")


def test_locator_builtin_matches_expected_strings() -> None:
    """Builtin scope locator strings must match the legacy output."""
    paths = SkillPaths(data_root="/data")
    loc = paths.locator("demo", SkillType.BUILTIN)
    assert loc.scope == SkillType.BUILTIN
    assert loc.host_skill_dir == "/data/skills/demo"
    assert loc.host_packages_dir == "/data/skill-packages/demo/python"
    assert loc.container_skill_dir == "/skills/demo"
    assert loc.container_packages_dir == "/skill-packages/demo/python"


def test_locator_tenant_matches_expected_strings() -> None:
    """Tenant scope locator strings must match the legacy output."""
    paths = SkillPaths(data_root="/data")
    loc = paths.locator("demo", SkillType.TENANT, tenant_id=7)
    assert loc.scope == SkillType.TENANT
    assert loc.host_skill_dir == "/data/tenants/tenant_7/skills/demo"
    assert loc.host_packages_dir == "/data/tenants/tenant_7/skill-packages/demo/python"
    assert loc.container_skill_dir == "/skills-tenant/demo"
    assert loc.container_packages_dir == "/skill-packages-tenant/demo/python"


def test_locator_personal_matches_expected_strings() -> None:
    """Personal scope locator strings must match the legacy output."""
    paths = SkillPaths(data_root="/data")
    loc = paths.locator("demo", SkillType.PERSONAL, tenant_id=7, user_id=9)
    assert loc.scope == SkillType.PERSONAL
    assert loc.host_skill_dir == "/data/tenants/tenant_7/workspace/user_9/skills/demo"
    assert loc.host_packages_dir is None
    assert loc.container_skill_dir == "/workspace/skills/demo"
    assert loc.container_packages_dir is None
