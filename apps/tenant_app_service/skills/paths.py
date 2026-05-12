"""Skill on-disk layout (host + container).

Single source of truth for where skills live on the host and inside the
sandbox container. Both ``SkillResolver`` (multi-scope resolution) and
``SkillRepository`` (CRUD) consume this module instead of building paths
inline.

The container-side strings are the bind-mount points used by the
sandbox controller (see ``apps/shared/sandbox/paths.py`` for the
host-side helpers the controller relies on).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apps.tenant_app_service.skills.domain import SkillLocator, SkillType

# Container-side mount points (must stay in sync with sandbox bind mounts).
CONTAINER_BUILTIN_DIR = "/skills"
CONTAINER_TENANT_DIR = "/skills-tenant"
CONTAINER_BUILTIN_PACKAGES_DIR = "/skill-packages"
CONTAINER_TENANT_PACKAGES_DIR = "/skill-packages-tenant"
# /workspace is already mounted, so personal skills ride on that.
CONTAINER_PERSONAL_DIR = "/workspace/skills"


@dataclass(frozen=True)
class SkillPaths:
    """Skill on-disk layout (host + container)."""

    data_root: str

    # --- host-side: built-in ---
    @property
    def builtin_dir(self) -> str:
        return str(Path(self.data_root) / "skills")

    def builtin_packages_dir(self, skill_name: str) -> str:
        return str(Path(self.data_root) / "skill-packages" / skill_name / "python")

    # --- host-side: tenant-scoped ---
    def tenant_skills_dir(self, tenant_id: int) -> str:
        return str(Path(self.data_root) / "tenants" / f"tenant_{tenant_id}" / "skills")

    def tenant_packages_dir(self, tenant_id: int) -> str:
        return str(Path(self.data_root) / "tenants" / f"tenant_{tenant_id}" / "skill-packages")

    def tenant_skill_dir(self, tenant_id: int, skill_name: str) -> str:
        return str(Path(self.tenant_skills_dir(tenant_id)) / skill_name)

    # --- host-side: personal ---
    def personal_skills_dir(self, tenant_id: int, user_id: int) -> str:
        return str(
            Path(self.data_root) / "tenants" / f"tenant_{tenant_id}" / "workspace" / f"user_{user_id}" / "skills"
        )

    def personal_skill_dir(self, tenant_id: int, user_id: int, skill_name: str) -> str:
        return str(Path(self.personal_skills_dir(tenant_id, user_id)) / skill_name)

    # --- locator builder ---
    def locator(
        self,
        skill_name: str,
        scope: SkillType,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> SkillLocator:
        """Build a :class:`SkillLocator` for one skill in one scope.

        The output strings must match the bind-mount contract; downstream
        tests in ``tests/unit/skills/test_paths.py`` lock the strings in.
        """
        if scope.value == "builtin":
            return SkillLocator(
                scope=scope,
                host_skill_dir=str(Path(self.builtin_dir) / skill_name),
                host_packages_dir=self.builtin_packages_dir(skill_name),
                container_skill_dir=f"{CONTAINER_BUILTIN_DIR}/{skill_name}",
                container_packages_dir=f"{CONTAINER_BUILTIN_PACKAGES_DIR}/{skill_name}/python",
            )
        if scope.value == "tenant":
            return SkillLocator(
                scope=scope,
                host_skill_dir=self.tenant_skill_dir(tenant_id, skill_name),
                host_packages_dir=(f"{self.tenant_packages_dir(tenant_id)}/{skill_name}/python"),
                container_skill_dir=f"{CONTAINER_TENANT_DIR}/{skill_name}",
                container_packages_dir=f"{CONTAINER_TENANT_PACKAGES_DIR}/{skill_name}/python",
            )
        # personal
        return SkillLocator(
            scope=scope,
            host_skill_dir=self.personal_skill_dir(tenant_id, user_id, skill_name),
            host_packages_dir=None,
            container_skill_dir=f"{CONTAINER_PERSONAL_DIR}/{skill_name}",
            container_packages_dir=None,
        )
