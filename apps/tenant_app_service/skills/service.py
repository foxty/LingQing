"""Skill management service.

Reuses the unified :class:`SkillResolver` for skill discovery across
all scopes and ``SkillConfigStore`` for per-skill ``config.json`` state
(enabled, env-var keys, audit fields). config.json is optional
metadata (env vars only) and is NOT a skill identifier.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, BinaryIO

from apps.config import EnvConfig
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import SkillConfig
from apps.tenant_app_service.skills.domain import (
    SkillPackageFetcherPort,
    SkillSourceRef,
    SkillType,
    parse_skill_source_url,
)
from apps.tenant_app_service.skills.dtos import SkillInfo
from apps.tenant_app_service.skills.paths import SkillPaths
from apps.tenant_app_service.skills.resolution import (
    SkillResolver,
    get_default_skill_resolver,
)

if TYPE_CHECKING:
    from apps.tenant_app_service.skills.resolution import SkillResolver

logger = get_logger(__name__)


class SkillService:
    def __init__(
        self,
        data_root: str | None = None,
        resolver: SkillResolver | None = None,
        package_fetcher: SkillPackageFetcherPort | None = None,
    ):
        from apps.tenant_app_service.skills.repository import (
            SkillConfigStore,
            SkillRepository,
        )
        from apps.tenant_app_service.skills.validator import SkillZipValidator

        self._data_root = data_root or EnvConfig.DATA_ROOT_PATH or "."
        self._paths = SkillPaths(data_root=self._data_root)
        # Share the process-wide SkillResolver so the management UI and
        # the agent runtime observe the same per-tenant cache.
        # Tests that need isolation pass their own resolver.
        self._resolver: SkillResolver = resolver or get_default_skill_resolver()
        self._repo = SkillRepository(self._data_root)
        self._config_store = SkillConfigStore(self._data_root)
        self._zip_validator = SkillZipValidator()
        # Tool registry for validation (injected from agent runtime)
        from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY

        self._tool_registry = TOOL_REGISTRY
        self._package_fetcher = package_fetcher

    def list_skills(self, tenant_id: int, user_id: int, type_filter: SkillType | None = None) -> list[SkillInfo]:
        """List skills, grouped per scope.

        Same name in different scopes is returned once per scope (no precedence
        collapsing) so the UI can group by type.
        """
        scopes: list[SkillType] = (
            [type_filter] if type_filter is not None else [SkillType.BUILTIN, SkillType.TENANT, SkillType.PERSONAL]
        )
        results: list[SkillInfo] = []
        for scope in scopes:
            merged = self._resolver.resolve(tenant_id=tenant_id, user_id=user_id, type_filter=scope)
            for name, skill in merged.items():
                results.append(self._to_info(skill))
        return results

    def get_skill(self, tenant_id: int, user_id: int, name: str) -> SkillInfo | None:
        """Return the highest-precedence skill with the given name."""
        merged = self._resolver.resolve(tenant_id=tenant_id, user_id=user_id)
        skill = merged.get(name)
        return self._to_info(skill) if skill is not None else None

    def create_skill(
        self, tenant_id: int, user_id: int, skill_type: SkillType, zip_file: BinaryIO, created_by: str
    ) -> SkillInfo:
        from apps.shared.core.exceptions import ValidationError

        if skill_type not in (SkillType.TENANT, SkillType.PERSONAL):
            raise ValidationError(f"Invalid skill type: {skill_type}. Must be 'tenant' or 'personal'")

        validation = self._zip_validator.validate_zip(zip_file)
        name = validation["name"]

        self._check_name_available(tenant_id, user_id, name)

        if skill_type == SkillType.TENANT:
            target_dir = self._repo.get_tenant_skill_dir(tenant_id, name)
        else:
            target_dir = self._repo.get_personal_skill_dir(tenant_id, user_id, name)

        if os.path.exists(target_dir):
            raise ValidationError(
                f"Skill '{name}' folder already exists but could not be loaded. "
                "Fix SKILL.md or delete the folder before re-importing."
            )

        self._extract_skill_zip(zip_file, target_dir)
        # Invalidate the resolver cache so the new skill shows up.
        self._resolver.clear_cache()

        return SkillInfo(
            name=name,
            type=skill_type,
            description=validation["description"],
            enabled=True,
            env_var_keys=[],
            created_by=created_by,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )

    def import_skill_from_url(
        self, tenant_id: int, user_id: int, skill_type: SkillType, url: str, created_by: str
    ) -> SkillInfo:
        ref = parse_skill_source_url(url)
        zip_file = self._fetch_remote_skill_package(ref)
        return self.create_skill(tenant_id, user_id, skill_type, zip_file, created_by)

    def _fetch_remote_skill_package(self, ref: SkillSourceRef) -> BinaryIO:
        from apps.tenant_app_service.skills.skill_source_fetcher import SkillSourceFetcher

        if self._package_fetcher is not None:
            return self._package_fetcher.fetch_as_zip(ref)

        with SkillSourceFetcher() as fetcher:
            return fetcher.fetch_as_zip(ref)

    def _check_name_available(self, tenant_id: int, user_id: int, name: str) -> None:
        """Validate skill name format and check for conflicts across all scopes."""
        from apps.shared.core.exceptions import DuplicateResourceError, ValidationError

        # 1. Validate name format (business rule)
        try:
            self._zip_validator.validate_skill_name(name)
        except ValidationError:
            raise  # Re-raise as-is, already a ValidationError

        # 2. Check for conflicts across all scopes using repository methods
        # Builtin scope
        builtin_configs = self._repo.load_builtin_skill_configs()
        if name in builtin_configs:
            raise DuplicateResourceError(f"Skill name '{name}' conflicts with an existing builtin skill")

        # Tenant scope
        tenant_configs = self._repo.load_tenant_skill_configs(tenant_id)
        if name in tenant_configs:
            raise DuplicateResourceError(f"Skill name '{name}' already exists in this tenant")

        # Personal scope
        personal_configs = self._repo.load_personal_skill_configs(tenant_id, user_id)
        if name in personal_configs:
            raise DuplicateResourceError(f"Skill name '{name}' already exists in your personal skills")

    def _extract_skill_zip(self, zip_file: BinaryIO, target_dir: str) -> None:
        """Extract ZIP file with path traversal protection (business rule)."""
        import tempfile
        import zipfile

        from apps.shared.core.exceptions import ValidationError

        zip_file.seek(0)
        raw = zip_file.read()
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(raw)
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                base_dir = self._find_skill_base(members)
                for member in members:
                    member_path = os.path.normpath(member)
                    if not member_path or member_path.endswith("/"):
                        continue
                    if member_path.startswith("..") or member_path.startswith("/"):
                        raise ValidationError(f"ZIP contains invalid path: {member}")
                    # Strip base_dir prefix so files land flat in target_dir
                    if base_dir and member_path.startswith(base_dir + "/"):
                        rel_path = member_path[len(base_dir) + 1 :]
                    elif base_dir and member_path == base_dir:
                        continue
                    else:
                        rel_path = member_path
                    if not rel_path:
                        continue
                    target_path = os.path.join(target_dir, rel_path)
                    if not target_path.startswith(os.path.normpath(target_dir)):
                        raise ValidationError(f"ZIP path traversal detected: {member}")
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    zf.extract(member, tmpdir)
                    import shutil

                    shutil.move(os.path.join(tmpdir, member), target_path)

    @staticmethod
    def _find_skill_base(members: list[str]) -> str | None:
        from apps.tenant_app_service.skills.domain import find_skill_md_base

        return find_skill_md_base(members)

    def _validate_skill_tools(self, skill: SkillConfig, tool_registry: dict[str, Any] | None = None) -> None:
        """Validate skill's tool references against registry (business rule).

        This is called after loading skills to ensure all referenced tools
        exist in the agent runtime. Tool validation is a service-layer
        concern, not a repository concern.
        """
        registry = tool_registry or self._tool_registry
        if not registry:
            return  # No registry available, skip validation

        for tool in skill.tools:
            if tool.name not in registry:
                from apps.shared.core.exceptions import ValidationError

                raise ValidationError(f"Skill '{skill.name}' references unknown tool '{tool.name}'")

    def delete_skill(self, tenant_id: int, user_id: int, skill_type: SkillType, name: str) -> None:
        from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError

        if skill_type == SkillType.TENANT:
            skill_dir = self._repo.get_tenant_skill_dir(tenant_id, name)
        elif skill_type == SkillType.PERSONAL:
            skill_dir = self._repo.get_personal_skill_dir(tenant_id, user_id, name)
        else:
            raise ValidationError("Only tenant and personal skills can be deleted")

        if not os.path.isdir(skill_dir):
            raise ResourceNotFoundError(f"Skill '{name}' not found in {skill_type} scope")

        self._repo.delete_skill_dir(skill_dir)
        self._resolver.clear_cache()

    def get_env_vars(self, tenant_id: int, user_id: int, scope: SkillType, skill_name: str) -> dict[str, str]:
        from apps.shared.core.exceptions import ValidationError

        if scope == SkillType.TENANT:
            skill_dir = self._repo.get_tenant_skill_dir(tenant_id, skill_name)
        elif scope == SkillType.PERSONAL:
            skill_dir = self._repo.get_personal_skill_dir(tenant_id, user_id, skill_name)
        else:
            raise ValidationError("Env vars are only supported for tenant and personal skills")
        return self._config_store.get_masked_env_vars(skill_dir, skill_name)

    def update_env_vars(
        self, tenant_id: int, user_id: int, scope: SkillType, skill_name: str, env_vars: dict[str, str]
    ) -> dict[str, str]:
        from apps.shared.core.exceptions import ValidationError

        if scope == SkillType.TENANT:
            skill_dir = self._repo.get_tenant_skill_dir(tenant_id, skill_name)
        elif scope == SkillType.PERSONAL:
            skill_dir = self._repo.get_personal_skill_dir(tenant_id, user_id, skill_name)
        else:
            raise ValidationError("Env vars are only supported for tenant and personal skills")
        config = self._config_store.update_env_vars(skill_dir, skill_name, env_vars)
        return {
            key: __import__("apps.shared.utils.field_cipher", fromlist=["FieldCipher"]).FieldCipher.mask_value(value)
            for key, value in config.env_vars.items()
        }

    def toggle_enabled(
        self, tenant_id: int, user_id: int, scope: SkillType, skill_name: str, enabled: bool
    ) -> SkillInfo:
        from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError

        if scope == SkillType.TENANT:
            skill_dir = self._repo.get_tenant_skill_dir(tenant_id, skill_name)
        elif scope == SkillType.PERSONAL:
            skill_dir = self._repo.get_personal_skill_dir(tenant_id, user_id, skill_name)
        else:
            raise ValidationError("Only tenant and personal skills can be toggled")
        self._config_store.toggle_enabled(skill_dir, skill_name, enabled)
        result = self.get_skill(tenant_id, user_id, skill_name)
        if result is None:
            raise ResourceNotFoundError(f"Skill '{skill_name}' not found")
        return result

    def get_decrypted_env_vars(self, tenant_id: int, user_id: int, scope: SkillType, skill_name: str) -> dict[str, str]:
        from apps.shared.core.exceptions import ValidationError

        if scope == SkillType.TENANT:
            skill_dir = self._repo.get_tenant_skill_dir(tenant_id, skill_name)
        elif scope == SkillType.PERSONAL:
            skill_dir = self._repo.get_personal_skill_dir(tenant_id, user_id, skill_name)
        else:
            raise ValidationError("Env vars are only supported for tenant and personal skills")
        return self._config_store.get_decrypted_env_vars(skill_dir, skill_name)

    def _to_info(self, skill: Any) -> SkillInfo:
        """Map a :class:`SkillConfig` to :class:`SkillInfo`.

        Enriches with ``config.json`` state (enabled, env-var keys, audit fields).
        """
        skill_dir = skill.locator.host_skill_dir if skill.locator else None
        config = self._config_store.read_config(skill_dir, skill.name) if skill_dir else None
        return SkillInfo(
            name=skill.name,
            type=skill.scope.value,
            description=skill.description or "",
            enabled=config.enabled if config else True,
            env_var_keys=list(config.env_vars.keys()) if config else [],
            created_by=config.created_by if config else "",
            created_at=config.created_at if config else "",
            updated_at=config.updated_at if config else "",
        )
