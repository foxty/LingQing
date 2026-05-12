"""Filesystem repository for skill management.

Single source of truth for skill file I/O. Loads skill from
``.yaml`` and ``SKILL.md`` formats with snapshot-based caching.
``config.json`` is optional metadata for env vars and should
NOT be used as a skill identifier.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.sandbox.paths import (
    get_personal_skills_dir,
    get_tenant_skills_dir,
)
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import (
    RETENTION_LONG_LIVED,
    RETENTION_TRANSIENT,
    TOOL_LIMIT_UNLIMITED,
    SkillConfig,
    ToolConfig,
)
from apps.tenant_app_service.skills.domain import SkillConfigData, SkillType
from apps.tenant_app_service.skills.paths import SkillPaths

logger = get_logger(__name__)

# Skill file format constants
STANDARD_SKILL_FILE = "SKILL.md"
STANDARD_SKILL_KNOWN_FIELDS = {
    "name",
    "description",
    "metadata",
    "allowed-tools",
    "tools",
    "scripts",
    "references",
    "assets",
    "display-name",
    "display_name",
}


class SkillConfigStore:
    """Reads/writes optional config.json (env vars only).

    config.json is NOT a skill identifier — it is an optional metadata
    file created only when the user configures env vars for a skill.
    Skills are identified by the presence of SKILL.md in their directory.
    """

    def __init__(self, data_root: str):
        self._data_root = data_root
        self._cipher = FieldCipher()

    def _config_path(self, skill_dir: str, skill_name: str) -> str:
        return os.path.join(skill_dir, f"{skill_name}.config.json")

    def read_config(self, skill_dir: str, skill_name: str) -> SkillConfigData | None:
        config_path = self._config_path(skill_dir, skill_name)
        if not os.path.isfile(config_path):
            return None
        try:
            with open(config_path, encoding="utf-8") as f:
                raw = f.read()
            config = SkillConfigData.from_json(raw)
            decrypted = {}
            for key, value in config.env_vars.items():
                try:
                    decrypted[key] = self._cipher.decrypt(value)
                except Exception:
                    decrypted[key] = value
            config.env_vars = decrypted
            return config
        except Exception as e:
            logger.warning("Failed to read config for skill '%s': %s", skill_name, e)
            return None

    def write_config(self, skill_dir: str, config: SkillConfigData) -> None:
        os.makedirs(skill_dir, exist_ok=True)
        config.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        encrypted = {}
        for key, value in config.env_vars.items():
            encrypted[key] = self._cipher.encrypt(value)
        config.env_vars = encrypted
        config_path = self._config_path(skill_dir, config.name)
        tmp_path = config_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(config.to_json())
            os.rename(tmp_path, config_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def update_env_vars(self, skill_dir: str, skill_name: str, env_vars: dict[str, str]) -> SkillConfigData:
        config = self.read_config(skill_dir, skill_name)
        if config is None:
            config = SkillConfigData(name=skill_name, type=SkillType.TENANT, description="")
        config.env_vars.update(env_vars)
        self.write_config(skill_dir, config)
        decrypted = {}
        for key, value in config.env_vars.items():
            try:
                decrypted[key] = self._cipher.decrypt(value)
            except Exception:
                decrypted[key] = value
        config.env_vars = decrypted
        return config

    def get_masked_env_vars(self, skill_dir: str, skill_name: str) -> dict[str, str]:
        config = self.read_config(skill_dir, skill_name)
        if config is None:
            return {}
        return {key: FieldCipher.mask_value(value) for key, value in config.env_vars.items()}

    def get_decrypted_env_vars(self, skill_dir: str, skill_name: str) -> dict[str, str]:
        config = self.read_config(skill_dir, skill_name)
        if config is None:
            return {}
        return dict(config.env_vars)

    def toggle_enabled(self, skill_dir: str, skill_name: str, enabled: bool) -> bool:
        config = self.read_config(skill_dir, skill_name)
        if config is None:
            config = SkillConfigData(name=skill_name, type=SkillType.TENANT, description="")
        config.enabled = enabled
        self.write_config(skill_dir, config)
        return config.enabled


class SkillRepository:
    """Filesystem repository for skill management.

    Single source of truth for skill file I/O. Parses both ``.yaml``
    and ``SKILL.md`` formats with snapshot-based caching.
    ``config.json`` is optional metadata for env vars.
    """

    def __init__(self, data_root: str, paths: SkillPaths | None = None):
        from apps.tenant_app_service.skills.paths import SkillPaths

        self._data_root = data_root
        self._paths = paths or SkillPaths(data_root=data_root)
        self._config_store = SkillConfigStore(data_root)
        # Per-directory cache for snapshot-based invalidation
        self._dir_caches: dict[str, tuple[dict[str, SkillConfig], tuple[tuple[str, int, int], ...]]] = {}

    def get_tenant_skills_root(self, tenant_id: int) -> str:
        return get_tenant_skills_dir(self._data_root, tenant_id)

    def get_tenant_skill_dir(self, tenant_id: int, skill_name: str) -> str:
        return os.path.join(self.get_tenant_skills_root(tenant_id), skill_name)

    def get_personal_skills_root(self, tenant_id: int, user_id: int) -> str:
        return get_personal_skills_dir(self._data_root, tenant_id, user_id)

    def get_personal_skill_dir(self, tenant_id: int, user_id: int, skill_name: str) -> str:
        return os.path.join(self.get_personal_skills_root(tenant_id, user_id), skill_name)

    def list_builtin_skills(self) -> list[dict[str, Any]]:
        return self._list_skill_dicts(self._paths.builtin_dir, SkillType.BUILTIN)

    def list_tenant_skills(self, tenant_id: int) -> list[dict[str, Any]]:
        skills_dir = get_tenant_skills_dir(self._data_root, tenant_id)
        return self._list_skill_dicts(skills_dir, SkillType.TENANT)

    def list_personal_skills(self, tenant_id: int, user_id: int) -> list[dict[str, Any]]:
        skills_dir = get_personal_skills_dir(self._data_root, tenant_id, user_id)
        return self._list_skill_dicts(skills_dir, SkillType.PERSONAL)

    # --- Scope-specific loading methods for resolver ---

    def load_builtin_skill_configs(self, force_reload: bool = False) -> dict[str, SkillConfig]:
        """Load all builtin skills with scope and locator tags."""
        configs = self.load_skill_configs(self._paths.builtin_dir, SkillType.BUILTIN, force_reload)
        for name, skill in configs.items():
            skill.scope = SkillType.BUILTIN
            skill.locator = self._paths.locator(name, SkillType.BUILTIN)
        return configs

    def load_tenant_skill_configs(self, tenant_id: int, force_reload: bool = False) -> dict[str, SkillConfig]:
        """Load all tenant skills with scope and locator tags."""
        skills_dir = self._paths.tenant_skills_dir(tenant_id)
        configs = self.load_skill_configs(skills_dir, SkillType.TENANT, force_reload)
        for name, skill in configs.items():
            skill.scope = SkillType.TENANT
            skill.locator = self._paths.locator(name, SkillType.TENANT, tenant_id=tenant_id)
        return configs

    def load_personal_skill_configs(
        self, tenant_id: int, user_id: int, force_reload: bool = False
    ) -> dict[str, SkillConfig]:
        """Load all personal skills with scope and locator tags."""
        skills_dir = self._paths.personal_skills_dir(tenant_id, user_id)
        configs = self.load_skill_configs(skills_dir, SkillType.PERSONAL, force_reload)
        for name, skill in configs.items():
            skill.scope = SkillType.PERSONAL
            skill.locator = self._paths.locator(name, SkillType.PERSONAL, tenant_id=tenant_id, user_id=user_id)
        return configs

    def _list_skill_dicts(self, skills_dir: str, scope: SkillType) -> list[dict[str, Any]]:
        """Load skills and convert to dict format for backward compatibility."""
        if not os.path.isdir(skills_dir):
            return []
        configs = self.load_skill_configs(skills_dir, scope)
        results: list[dict[str, Any]] = []
        for skill_config in configs.values():
            config = self._config_store.read_config(os.path.join(skills_dir, skill_config.name), skill_config.name)
            results.append(
                {
                    "name": skill_config.name,
                    "description": skill_config.description,
                    "enabled": config.enabled if config else True,
                    "env_var_keys": list(config.env_vars.keys()) if config else [],
                }
            )
        return results

    def load_skill_configs(
        self, skills_dir: str, scope: SkillType, force_reload: bool = False
    ) -> dict[str, SkillConfig]:
        """Load all skill configs from directory with snapshot-based caching.

        This is the single source of truth for reading skill files. Returns
        domain SkillConfig objects without tool_registry validation (that's
        a service-layer concern).
        """
        skills_path = Path(skills_dir)
        cache_key = str(skills_path)
        if not skills_path.exists():
            if cache_key in self._dir_caches and not force_reload:
                return self._dir_caches[cache_key][0]
            logger.debug("Skill directory not found, treating as empty: %s", skills_dir)
            empty: dict[str, SkillConfig] = {}
            self._dir_caches[cache_key] = (empty, ())
            return empty

        # Build snapshot for cache invalidation
        discovered_paths = self._discover_skill_paths(skills_path)
        current_snapshot = self._build_snapshot(skills_path, discovered_paths)

        # Check cache
        if cache_key in self._dir_caches and not force_reload:
            cached_configs, cached_snapshot = self._dir_caches[cache_key]
            if cached_snapshot == current_snapshot:
                return cached_configs
            logger.info("Skill cache invalidated for %s", skills_dir)

        # Load all skills
        loaded: dict[str, SkillConfig] = {}
        for path in sorted(skills_path.iterdir(), key=lambda p: p.name):
            skill: SkillConfig | None = None
            if path.is_file() and path.suffix == ".yaml":
                skill = self._load_legacy_yaml(path, scope)
            elif path.is_dir() and (path / STANDARD_SKILL_FILE).exists():
                try:
                    skill = self._load_standard_skill_dir(path, scope)
                except ValueError as exc:
                    logger.warning("Skipping invalid skill at %s: %s", path, exc)
                    continue

            if skill is None:
                continue

            if skill.name in loaded:
                raise ValueError(
                    f"Duplicate skill name '{skill.name}' found in both "
                    f"'{loaded[skill.name].source_file}' and '{skill.source_file}'."
                )
            loaded[skill.name] = skill

        # Update cache
        self._dir_caches[cache_key] = (loaded, current_snapshot)
        logger.info("Loaded %d skills from %s", len(loaded), skills_dir)
        return loaded

    def load_skill_config(self, skills_dir: str, name: str, scope: SkillType) -> SkillConfig | None:
        """Load a single skill config by name."""
        return self.load_skill_configs(skills_dir, scope).get(name)

    def clear_cache(self) -> None:
        """Clear all directory caches (e.g., after skill create/delete)."""
        self._dir_caches.clear()

    def _discover_skill_paths(self, skills_dir: Path) -> list[Path]:
        """Discover loadable skill config paths in deterministic order."""
        if not skills_dir.exists():
            return []

        discovered: list[Path] = []
        for path in sorted(skills_dir.iterdir(), key=lambda p: p.name):
            if path.is_file() and path.suffix == ".yaml":
                discovered.append(path)
            elif path.is_dir() and (path / STANDARD_SKILL_FILE).exists():
                discovered.append(path / STANDARD_SKILL_FILE)
        return discovered

    def _build_snapshot(self, skills_dir: Path, paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
        """Build cache snapshot from loadable skill config files."""
        snapshot: list[tuple[str, int, int]] = []
        for path in paths:
            stat = path.stat()
            rel = str(path.relative_to(skills_dir))
            snapshot.append((rel, stat.st_mtime_ns, stat.st_size))
        return tuple(snapshot)

    def _load_legacy_yaml(self, file_path: Path, scope: SkillType) -> SkillConfig:
        """Parse and validate one legacy YAML skill file.

        Note: Tool registry validation is NOT performed here. It's a
        service-layer concern that happens after loading.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in skill file '{file_path}': {e}") from e

        if not isinstance(raw, dict):
            raise ValueError(f"Skill file '{file_path}' must contain a YAML object at top level")

        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Skill file '{file_path}' must define non-empty string field 'name'")
        name = name.strip()

        system_prompt = raw.get("system_prompt")
        if not isinstance(system_prompt, str):
            raise ValueError(f"Skill '{name}' in '{file_path}' must define string field 'system_prompt'")

        description = raw.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"Skill '{name}' in '{file_path}' field 'description' must be string")

        api_refs_raw = raw.get("api_refs", [])
        if not isinstance(api_refs_raw, list):
            raise ValueError(f"Skill '{name}' in '{file_path}' field 'api_refs' must be a list")

        api_refs: list[str] = []
        for idx, ref in enumerate(api_refs_raw):
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError(f"Skill '{name}' in '{file_path}' api_refs entry #{idx} must be non-empty string")
            api_refs.append(ref.strip())

        tools_raw = raw.get("tools", [])
        if not isinstance(tools_raw, list):
            raise ValueError(f"Skill '{name}' in '{file_path}' field 'tools' must be a list")

        tools: list[ToolConfig] = []
        for idx, tool_def in enumerate(tools_raw):
            if not isinstance(tool_def, dict):
                raise ValueError(
                    f"Skill '{name}' in '{file_path}' tool entry #{idx} must be an object with at least 'name'"
                )

            tool_name = tool_def.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError(
                    f"Skill '{name}' in '{file_path}' tool entry #{idx} must define non-empty string field 'name'"
                )

            # NOTE: Tool registry validation removed - happens in service layer
            raw_limit = tool_def.get("limit", 0)
            if not isinstance(raw_limit, int) or raw_limit < 0:
                raise ValueError(
                    f"Skill '{name}' in '{file_path}' tool '{tool_name}' field 'limit' must be integer >= 0"
                )
            limit = raw_limit or TOOL_LIMIT_UNLIMITED

            hitl = tool_def.get("hitl", {})
            if not isinstance(hitl, dict):
                raise ValueError(f"Skill '{name}' in '{file_path}' tool '{tool_name}' field 'hitl' must be an object")

            result_retention = tool_def.get("result_retention", RETENTION_TRANSIENT)
            if result_retention not in (RETENTION_TRANSIENT, RETENTION_LONG_LIVED):
                raise ValueError(
                    f"Skill '{name}' in '{file_path}' tool '{tool_name}' field 'result_retention' "
                    f"must be '{RETENTION_TRANSIENT}' or '{RETENTION_LONG_LIVED}'"
                )

            cacheable = tool_def.get("cacheable", False)
            if not isinstance(cacheable, bool):
                raise ValueError(
                    f"Skill '{name}' in '{file_path}' tool '{tool_name}' field 'cacheable' must be boolean"
                )

            cache_invalidates = tool_def.get("cache_invalidates", [])
            if not isinstance(cache_invalidates, list) or not all(isinstance(s, str) for s in cache_invalidates):
                raise ValueError(
                    f"Skill '{name}' in '{file_path}' tool '{tool_name}' field 'cache_invalidates' "
                    f"must be a list of tool name strings"
                )

            tools.append(
                ToolConfig(
                    name=tool_name,
                    limit=limit,
                    hitl=hitl,
                    result_retention=result_retention,
                    cacheable=cacheable,
                    cache_invalidates=cache_invalidates,
                )
            )

        skill = SkillConfig(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            api_refs=api_refs,
            source_file=str(file_path),
            source_format="legacy_yaml",
            scope=scope,
        )
        return skill

    def _load_standard_skill_dir(self, skill_dir: Path, scope: SkillType) -> SkillConfig:
        """Parse one standard skill directory (name validation happens in service layer)."""
        skill_file = skill_dir / STANDARD_SKILL_FILE
        content = skill_file.read_text(encoding="utf-8")

        frontmatter, body = self._parse_skill_markdown(content, skill_file)
        # Extract name from frontmatter (validation is service-layer concern)
        name = frontmatter.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Skill in '{skill_file}' must define non-empty 'name' in frontmatter")
        name = name.strip()
        if name != skill_dir.name:
            logger.warning(
                "Skill name '%s' in frontmatter does not match directory name '%s' in '%s'",
                name,
                skill_dir.name,
                skill_file,
            )
        self._warn_unknown_standard_fields(frontmatter, name, skill_file)
        description = self._parse_standard_description(frontmatter, name, skill_file)
        metadata = self._parse_standard_metadata(frontmatter, name, skill_file)
        tools = self._parse_standard_allowed_tools(frontmatter, name, skill_file)

        if not isinstance(body, str) or not body.strip():
            raise ValueError(f"Skill '{name}' in '{skill_file}' must include non-empty markdown body")

        skill = SkillConfig(
            name=name,
            description=description,
            system_prompt=body.strip(),
            tools=tools,
            source_file=str(skill_file),
            source_format="standard_skill",
            skill_metadata=metadata,
            scope=scope,
        )
        return skill

    def _parse_skill_markdown(self, content: str, skill_file: Path) -> tuple[dict[str, Any], str]:
        """Parse SKILL.md content into YAML frontmatter and markdown body."""
        normalized_content = content.lstrip("\ufeff")
        lines = normalized_content.splitlines()

        start_idx = 0
        while start_idx < len(lines) and not lines[start_idx].strip():
            start_idx += 1

        if start_idx >= len(lines) or lines[start_idx].strip() != "---":
            raise ValueError(f"Standard skill file '{skill_file}' must start with frontmatter delimiter '---'")

        end_idx = None
        for idx in range(start_idx + 1, len(lines)):
            if lines[idx].strip() == "---":
                end_idx = idx
                break

        if end_idx is None:
            raise ValueError(f"Standard skill file '{skill_file}' has unclosed YAML frontmatter")

        frontmatter_text = "\n".join(lines[start_idx + 1 : end_idx])
        body_text = "\n".join(lines[end_idx + 1 :]) if end_idx + 1 < len(lines) else ""

        try:
            frontmatter = yaml.safe_load(frontmatter_text) if frontmatter_text.strip() else {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter in '{skill_file}': {e}") from e

        if not isinstance(frontmatter, dict):
            raise ValueError(f"Frontmatter in '{skill_file}' must be a YAML object")

        return frontmatter, body_text

    def _warn_unknown_standard_fields(self, frontmatter: dict[str, Any], name: str, skill_file: Path) -> None:
        """Log warnings for unknown fields in standard skill frontmatter."""
        unknown = set(frontmatter.keys()) - STANDARD_SKILL_KNOWN_FIELDS
        if unknown:
            logger.warning(
                "Skill '%s' in '%s' has unknown frontmatter fields: %s",
                name,
                skill_file,
                sorted(unknown),
            )

    def _parse_standard_description(self, frontmatter: dict[str, Any], name: str, skill_file: Path) -> str:
        """Extract description from standard skill frontmatter."""
        description = frontmatter.get("description", "")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Skill '{name}' in '{skill_file}' must define non-empty 'description'")
        return description.strip()

    def _parse_standard_metadata(self, frontmatter: dict[str, Any], name: str, skill_file: Path) -> dict[str, Any]:
        """Extract metadata from standard skill frontmatter."""
        metadata = frontmatter.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Skill '{name}' in '{skill_file}' field 'metadata' must be an object")
        return metadata

    @staticmethod
    def _parse_tool_name_and_limit(entry: str) -> tuple[str, int]:
        """Parse tool_name or tool_name:limit where limit is a trailing integer only."""
        stripped = entry.strip()
        match = re.fullmatch(r"([^:]+):(\d+)", stripped)
        if match:
            return match.group(1).strip(), int(match.group(2)) or TOOL_LIMIT_UNLIMITED
        return stripped, TOOL_LIMIT_UNLIMITED

    def _parse_standard_allowed_tools(
        self, frontmatter: dict[str, Any], name: str, skill_file: Path
    ) -> list[ToolConfig]:
        """Parse allowed-tools from standard skill frontmatter.

        Note: Tool registry validation is NOT performed here. It's a
        service-layer concern that happens after loading.
        """
        tools_config = frontmatter.get("tools")
        if tools_config is not None:
            if not isinstance(tools_config, list):
                raise ValueError(f"Skill '{name}' in '{skill_file}' field 'tools' must be a list")
            tools_raw: list[Any] = tools_config
        else:
            allowed_tools = frontmatter.get("allowed-tools", "")
            if isinstance(allowed_tools, str):
                if "," in allowed_tools:
                    tools_raw = [part.strip() for part in allowed_tools.split(",") if part.strip()]
                else:
                    tools_raw = [part.strip() for part in re.split(r"\s+", allowed_tools) if part.strip()]
            elif isinstance(allowed_tools, list):
                tools_raw = allowed_tools
            elif allowed_tools is None:
                tools_raw = []
            else:
                raise ValueError(
                    f"Skill '{name}' in '{skill_file}' field 'allowed-tools' must be a string or list"
                )

        tools: list[ToolConfig] = []
        for idx, tool_entry in enumerate(tools_raw):
            if isinstance(tool_entry, str):
                tool_name, limit = self._parse_tool_name_and_limit(tool_entry)
                tools.append(ToolConfig(name=tool_name, limit=limit))
            elif isinstance(tool_entry, dict):
                # Object format: {name: "tool", limit: 5, ...}
                tool_name = tool_entry.get("name")
                if not isinstance(tool_name, str) or not tool_name.strip():
                    raise ValueError(f"Skill '{name}' in '{skill_file}' tool entry #{idx} must define non-empty 'name'")
                tool_name = tool_name.strip()

                raw_limit = tool_entry.get("limit", 0)
                if not isinstance(raw_limit, int) or raw_limit < 0:
                    raise ValueError(
                        f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'limit' must be integer >= 0"
                    )
                limit = raw_limit or TOOL_LIMIT_UNLIMITED

                hitl = tool_entry.get("hitl", {})
                if not isinstance(hitl, dict):
                    raise ValueError(
                        f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'hitl' must be an object"
                    )

                result_retention = tool_entry.get("result_retention", RETENTION_TRANSIENT)
                if result_retention not in (RETENTION_TRANSIENT, RETENTION_LONG_LIVED):
                    raise ValueError(
                        f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'result_retention' "
                        f"must be '{RETENTION_TRANSIENT}' or '{RETENTION_LONG_LIVED}'"
                    )

                cacheable = tool_entry.get("cacheable", False)
                if not isinstance(cacheable, bool):
                    raise ValueError(
                        f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'cacheable' must be boolean"
                    )

                cache_invalidates = tool_entry.get("cache_invalidates", [])
                if not isinstance(cache_invalidates, list) or not all(isinstance(s, str) for s in cache_invalidates):
                    raise ValueError(
                        f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'cache_invalidates' "
                        f"must be a list of tool name strings"
                    )

                tools.append(
                    ToolConfig(
                        name=tool_name,
                        limit=limit,
                        hitl=hitl,
                        result_retention=result_retention,
                        cacheable=cacheable,
                        cache_invalidates=cache_invalidates,
                    )
                )
            else:
                raise ValueError(f"Skill '{name}' in '{skill_file}' tool entry #{idx} must be string or object")

        return tools

    def toggle_enabled(self, skill_dir: str, skill_name: str, enabled: bool) -> bool:
        return self._config_store.toggle_enabled(skill_dir, skill_name, enabled)

    def delete_skill_dir(self, skill_dir: str) -> None:
        if not os.path.isdir(skill_dir):
            raise ResourceNotFoundError(f"Skill directory not found: {skill_dir}")
        shutil.rmtree(skill_dir)
