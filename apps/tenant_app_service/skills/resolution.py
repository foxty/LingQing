"""Skill resolver for multi-granularity skill loading.

Resolves skills across builtin/tenant/personal scopes. All resolution is
runtime-scoped by ``tenant_id``/``user_id``.

The resolver is the single cache owner used by both the management router
(``SkillService.list_skills``/``get_skill``) and the agent runtime
(``AgentConfig.get_resolved_skills``). Per-scope reads are supported
via ``type_filter`` so the management UI can list builtin/tenant/personal
buckets separately.

Note: Skill name conflicts are prevented at creation time by
``SkillService._check_name_available()``, so no merge/precedence logic
is needed here. Each skill name is unique across all scopes.
"""

from __future__ import annotations

from typing import Any

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import SkillConfig
from apps.tenant_app_service.skills.domain import SkillLocator, SkillType

logger = get_logger(__name__)


class SkillResolver:
    """Resolves skills across builtin/tenant/personal scopes.

    Skill loading is delegated to ``SkillRepository`` which uses
    file-snapshot-based auto-invalidation. Because the repository is
    reused across calls, skills created outside the management UI
    (e.g. by an agent writing directly to the filesystem) show up on
    the next ``resolve()`` without explicit cache invalidation.

    Note: Name conflicts across scopes are prevented at creation time,
    so no precedence/merge logic is needed.
    """

    def __init__(
        self,
        data_root: str,
        tool_registry: dict[str, Any] | None = None,
    ):
        from apps.tenant_app_service.skills.repository import SkillRepository

        self._tool_registry = tool_registry or {}
        self._repo = SkillRepository(data_root)

    def resolve(
        self,
        tenant_id: int | None = None,
        user_id: int | None = None,
        force_reload: bool = False,
        type_filter: SkillType | None = None,
    ) -> dict[str, SkillConfig]:
        """Load skills from all applicable scopes.

        Args:
            tenant_id: Tenant scope; if ``None`` only builtin skills are loaded.
            user_id: User scope (within tenant); required for personal skills.
            force_reload: Bypass snapshot cache and re-read from disk.
            type_filter: If given, return only skills whose scope matches.

        Returns:
            Mapping ``skill_name -> SkillConfig``. Each skill is tagged with
            its scope. Since name conflicts are prevented at creation time,
            each name appears at most once.
        """
        all_skills: dict[str, SkillConfig] = {}

        # 1. Builtin skills (always loaded)
        all_skills.update(self._repo.load_builtin_skill_configs(force_reload))

        # 2. Tenant skills (if tenant_id provided)
        if tenant_id is not None:
            all_skills.update(self._repo.load_tenant_skill_configs(tenant_id, force_reload))

        # 3. Personal skills (if both tenant_id and user_id provided)
        if tenant_id is not None and user_id is not None:
            all_skills.update(self._repo.load_personal_skill_configs(tenant_id, user_id, force_reload))

        # Filter by scope if requested
        if type_filter is not None:
            return {name: skill for name, skill in all_skills.items() if skill.scope == type_filter}

        return all_skills

    def locate(
        self,
        skill_name: str,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> SkillLocator | None:
        """Get the ``SkillLocator`` for a skill by name."""
        skill = self.resolve(tenant_id=tenant_id, user_id=user_id).get(skill_name)
        return skill.locator if skill else None

    def clear_cache(self) -> None:
        """Drop all snapshot caches.

        Use after a config reload or when a skill is created/deleted via the management API.
        """
        self._repo.clear_cache()


# ---------------------------------------------------------------------------
# Shared singleton factory
# ---------------------------------------------------------------------------
#
# The resolver is intentionally shared between ``SkillService`` (CRUD) and the
# agent runtime (``AgentConfig`` / ``read_skill_file``) so they observe
# the same per-tenant cache and the same on-disk state. Tests that need
# isolation should instantiate their own ``SkillResolver`` rather than relying
# on this singleton.

_default_skill_resolver: SkillResolver | None = None
_default_skill_resolver_lock = None  # lazy: stdlib threading isn't always available at import


def get_default_skill_resolver() -> SkillResolver:
    """Return the process-wide :class:`SkillResolver` singleton.

    Lazy-imports the tool registry / env config to avoid import cycles.
    """
    global _default_skill_resolver
    if _default_skill_resolver is None:
        from apps.config import EnvConfig
        from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY

        _default_skill_resolver = SkillResolver(
            data_root=EnvConfig.DATA_ROOT_PATH or ".",
            tool_registry=TOOL_REGISTRY,
        )
    return _default_skill_resolver


def reset_default_skill_resolver() -> None:
    """Drop the cached default resolver. Test-only."""
    global _default_skill_resolver
    _default_skill_resolver = None
