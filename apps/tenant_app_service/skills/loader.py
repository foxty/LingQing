"""Loader for skill configuration files.

This loader reads skill definitions from ``config/skills`` and supports:
1. Legacy YAML format: ``*.yaml``
2. Standard skill directory format: ``<skill_dir>/SKILL.md``

All formats are normalized into ``SkillConfig`` used by ``AgentConfig``
and ``SkillResolver``.
"""

import re
from pathlib import Path
from typing import Any

import yaml

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import (
    RETENTION_LONG_LIVED,
    RETENTION_TRANSIENT,
    TOOL_LIMIT_UNLIMITED,
    SkillConfig,
    ToolConfig,
)
from apps.tenant_app_service.skills.domain import SkillType

logger = get_logger(__name__)
STANDARD_SKILL_FILE = "SKILL.md"
STANDARD_SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
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


class SkillConfigLoader:
    """Load and validate skill definitions from mixed formats.

    .. deprecated::
        Use :class:`SkillRepository.load_skill_configs()` instead.
        This class is kept for backward compatibility during migration
        and will be removed in a future version.

    The ``scope`` parameter records which scope the directory represents
    (builtin / tenant / personal). The loader is otherwise scope-agnostic;
    scope-based merging and locator construction live in ``SkillResolver``
    and ``SkillPaths`` respectively.
    """

    def __init__(
        self,
        skills_dir: str = "config/skills",
        tool_registry: dict[str, Any] | None = None,
        scope: SkillType = SkillType.BUILTIN,
    ):
        import warnings

        warnings.warn(
            "SkillConfigLoader is deprecated. Use SkillRepository.load_skill_configs() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.skills_dir = Path(skills_dir)
        self.tool_registry = tool_registry
        self.scope = scope
        self._cache: dict[str, SkillConfig] | None = None
        self._cache_snapshot: tuple[tuple[str, int, int], ...] | None = None

    def _discover_skill_paths(self) -> list[Path]:
        """Discover loadable skill config paths in deterministic order."""
        if not self.skills_dir.exists():
            return []

        discovered: list[Path] = []
        for path in sorted(self.skills_dir.iterdir(), key=lambda p: p.name):
            if path.is_file() and path.suffix == ".yaml":
                discovered.append(path)
            elif path.is_dir() and (path / STANDARD_SKILL_FILE).exists():
                discovered.append(path / STANDARD_SKILL_FILE)
        return discovered

    def _build_snapshot(self, paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
        """Build cache snapshot from loadable skill config files.

        Snapshot dimensions are enough for auto invalidation while keeping it cheap:
        relative path, mtime nanoseconds and file size.
        """
        snapshot: list[tuple[str, int, int]] = []
        for path in paths:
            stat = path.stat()
            rel = str(path.relative_to(self.skills_dir))
            snapshot.append((rel, stat.st_mtime_ns, stat.st_size))
        return tuple(snapshot)

    def load_all(self, force_reload: bool = False) -> dict[str, SkillConfig]:
        """Load all skill definitions under ``skills_dir``.

        Args:
            force_reload: Whether to bypass cache and reload from disk.

        Returns:
            Mapping ``skill_name -> SkillConfig``.
        """
        if not self.skills_dir.exists():
            logger.info("Skill directory not found, returning empty skills: %s", self.skills_dir)
            self._cache = {}
            self._cache_snapshot = ()
            return self._cache

        discovered_paths = self._discover_skill_paths()
        current_snapshot = self._build_snapshot(discovered_paths)
        if self._cache is not None and not force_reload:
            if self._cache_snapshot == current_snapshot:
                return self._cache
            logger.info("Skill cache invalidated due to source file changes under %s", self.skills_dir)

        loaded: dict[str, SkillConfig] = {}
        for path in sorted(self.skills_dir.iterdir(), key=lambda p: p.name):
            skill: SkillConfig | None = None
            if path.is_file() and path.suffix == ".yaml":
                skill = self._load_legacy_yaml(path)
            elif path.is_dir() and (path / STANDARD_SKILL_FILE).exists():
                skill = self._load_standard_skill_dir(path)

            if skill is None:
                continue

            if skill.name in loaded:
                raise ValueError(
                    f"Duplicate skill name '{skill.name}' found in both "
                    f"'{loaded[skill.name].source_file}' and '{skill.source_file}'."
                )
            loaded[skill.name] = skill

        self._cache = loaded
        self._cache_snapshot = current_snapshot
        logger.info("Loaded skills: %s config(s) from %s", list(loaded.keys()), self.skills_dir)
        return loaded

    def get_skill(self, name: str) -> SkillConfig | None:
        """Get one skill by name."""
        return self.load_all().get(name)

    def reload(self) -> dict[str, SkillConfig]:
        """Force reload all skill files."""
        return self.load_all(force_reload=True)

    def _load_legacy_yaml(self, file_path: Path) -> SkillConfig:
        """Parse and validate one legacy YAML skill file."""
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

            if self.tool_registry is not None and tool_name not in self.tool_registry:
                raise ValueError(f"Skill '{name}' in '{file_path}' references unknown tool '{tool_name}'")

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
            scope=self.scope,
        )
        return skill

    def _load_standard_skill_dir(self, skill_dir: Path) -> SkillConfig:
        """Parse and validate one standard skill directory."""
        skill_file = skill_dir / STANDARD_SKILL_FILE
        content = skill_file.read_text(encoding="utf-8")

        frontmatter, body = self._parse_skill_markdown(content, skill_file)
        name = self._parse_standard_skill_name(frontmatter, skill_dir, skill_file)
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
            scope=self.scope,
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
        body = "\n".join(lines[end_idx + 1 :])

        try:
            raw_frontmatter = yaml.safe_load(frontmatter_text) if frontmatter_text.strip() else {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid frontmatter YAML in '{skill_file}': {e}") from e

        if not isinstance(raw_frontmatter, dict):
            raise ValueError(f"Frontmatter in '{skill_file}' must be a YAML object")

        return raw_frontmatter, body

    def _warn_unknown_standard_fields(self, frontmatter: dict[str, Any], name: str, skill_file: Path) -> None:
        unknown_fields = [key for key in frontmatter.keys() if key not in STANDARD_SKILL_KNOWN_FIELDS]
        for field_name in sorted(unknown_fields):
            logger.warning(
                "Skill '%s' in '%s' contains unknown frontmatter field '%s'; ignoring",
                name,
                skill_file,
                field_name,
            )

    def _parse_standard_skill_name(self, frontmatter: dict[str, Any], skill_dir: Path, skill_file: Path) -> str:
        """Parse and validate standard skill name from frontmatter ``name``."""
        name = frontmatter.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Skill '{skill_file}' must define non-empty string field 'name'")

        name = name.strip()
        if len(name) > 64:
            raise ValueError(f"Skill '{name}' in '{skill_file}' field 'name' must be <= 64 chars")
        if "--" in name or not STANDARD_SKILL_NAME_RE.match(name):
            raise ValueError(
                f"Skill '{name}' in '{skill_file}' field 'name' must contain only lowercase letters, "
                "digits, and single hyphens"
            )
        if skill_dir.name != name:
            raise ValueError(
                f"Skill '{name}' in '{skill_file}' must match its parent directory name '{skill_dir.name}'"
            )
        return name

    def _parse_standard_description(self, frontmatter: dict[str, Any], name: str, skill_file: Path) -> str:
        """Parse and validate standard skill description."""
        description = frontmatter.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Skill '{name}' in '{skill_file}' must define non-empty string field 'description'")

        description = description.strip()
        if len(description) > 1024:
            raise ValueError(f"Skill '{name}' in '{skill_file}' field 'description' must be <= 1024 chars")
        return description

    def _parse_standard_metadata(self, frontmatter: dict[str, Any], name: str, skill_file: Path) -> dict[str, str]:
        """Parse optional metadata for standard skill."""
        metadata = frontmatter.get("metadata", {})
        if metadata is None:
            return {}
        if not isinstance(metadata, dict):
            raise ValueError(f"Skill '{name}' in '{skill_file}' field 'metadata' must be an object")

        normalized: dict[str, str] = {}
        for key, value in metadata.items():
            if not isinstance(key, str) or not isinstance(value, str):
                logger.warning(
                    "Skill '%s' in '%s' metadata entry '%s' has non-string key or value; skipping",
                    name,
                    skill_file,
                    key,
                )
                continue
            normalized[key] = value
        return normalized

    def _parse_standard_allowed_tools(
        self, frontmatter: dict[str, Any], name: str, skill_file: Path
    ) -> list[ToolConfig]:
        """Parse optional allowed-tools or tools from standard skill frontmatter.

        Supports two formats:
        1. Simple list: allowed-tools: [tool1, tool2]
        2. Structured config: tools: [{name: tool1, limit: 5, ...}]
        """
        # Check for structured tools configuration first
        tools_config = frontmatter.get("tools")
        if tools_config is not None:
            return self._parse_structured_tools(tools_config, name, skill_file)

        # Fall back to simple allowed-tools format
        allowed_tools = frontmatter.get("allowed-tools", "")

        allowed_names: list[str]
        if isinstance(allowed_tools, str):
            allowed_names = [candidate.strip() for candidate in re.split(r"[\s,]+", allowed_tools) if candidate.strip()]
        elif isinstance(allowed_tools, list):
            allowed_names = []
            for idx, value in enumerate(allowed_tools):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Skill '{name}' in '{skill_file}' field 'allowed-tools' entry #{idx} must be non-empty string"
                    )
                allowed_names.append(value.strip())
        elif allowed_tools is None:
            allowed_names = []
        else:
            raise ValueError(
                f"Skill '{name}' in '{skill_file}' field 'allowed-tools' must be a string or list of strings"
            )

        tools: list[ToolConfig] = []
        seen: set[str] = set()
        for tool_name in allowed_names:
            if tool_name in seen:
                continue
            seen.add(tool_name)

            if self.tool_registry is not None and tool_name not in self.tool_registry:
                logger.warning(
                    "Skill '%s' in '%s' references unmapped allowed-tool '%s'; skipping",
                    name,
                    skill_file,
                    tool_name,
                )
                continue

            tools.append(ToolConfig(name=tool_name, limit=TOOL_LIMIT_UNLIMITED))

        return tools

    def _parse_structured_tools(self, tools_config: Any, name: str, skill_file: Path) -> list[ToolConfig]:
        """Parse structured tools configuration with full metadata support."""
        if not isinstance(tools_config, list):
            raise ValueError(f"Skill '{name}' in '{skill_file}' field 'tools' must be a list of tool configurations")

        tools: list[ToolConfig] = []
        seen: set[str] = set()

        for idx, tool_def in enumerate(tools_config):
            if not isinstance(tool_def, dict):
                raise ValueError(f"Skill '{name}' in '{skill_file}' tools entry #{idx} must be an object")

            tool_name = tool_def.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError(
                    f"Skill '{name}' in '{skill_file}' tools entry #{idx} must define non-empty string field 'name'"
                )
            tool_name = tool_name.strip()

            if tool_name in seen:
                logger.warning(
                    "Skill '%s' in '%s' has duplicate tool '%s'; using first occurrence",
                    name,
                    skill_file,
                    tool_name,
                )
                continue
            seen.add(tool_name)

            if self.tool_registry is not None and tool_name not in self.tool_registry:
                logger.warning(
                    "Skill '%s' in '%s' references unmapped tool '%s'; skipping",
                    name,
                    skill_file,
                    tool_name,
                )
                continue

            # Parse limit
            raw_limit = tool_def.get("limit", 0)
            if not isinstance(raw_limit, int) or raw_limit < 0:
                raise ValueError(
                    f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'limit' must be integer >= 0"
                )
            limit = raw_limit or TOOL_LIMIT_UNLIMITED

            # Parse hitl
            hitl = tool_def.get("hitl", {})
            if not isinstance(hitl, dict):
                raise ValueError(f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'hitl' must be an object")

            # Parse result_retention
            result_retention = tool_def.get("result_retention", RETENTION_TRANSIENT)
            if result_retention not in (RETENTION_TRANSIENT, RETENTION_LONG_LIVED):
                raise ValueError(
                    f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'result_retention' "
                    f"must be '{RETENTION_TRANSIENT}' or '{RETENTION_LONG_LIVED}'"
                )

            # Parse cacheable
            cacheable = tool_def.get("cacheable", False)
            if not isinstance(cacheable, bool):
                raise ValueError(
                    f"Skill '{name}' in '{skill_file}' tool '{tool_name}' field 'cacheable' must be boolean"
                )

            # Parse cache_invalidates
            cache_invalidates = tool_def.get("cache_invalidates", [])
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

        return tools
