"""Bound agent config: locked document plus runtime skill/tool/prompt resolution."""

from typing import Any, Dict, List

from langchain_core.tools import BaseTool

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import (
    AgentLoadedConfig,
    AgentRuntimeContext,
    SkillConfig,
    ToolConfig,
)
from apps.tenant_app_service.agents.skills.tool_resolver import resolve_effective_skill_tools

logger = get_logger(__name__)


class AgentConfig:
    """Read-only view of a locked agent document, plus runtime skill/tool/prompt binding."""

    def __init__(
        self,
        config: AgentLoadedConfig,
        *,
        config_overrides: Dict[str, Any] | None = None,
    ):
        """Consume a resolved agent document. Does not load YAML or catalog.

        Args:
            config: YAML-shaped agent document (``agent_id`` is a field, not a lookup key)
            config_overrides: Optional dict to overlay on the document
        """
        if "agent_id" not in config:
            raise ValueError("AgentLoadedConfig requires agent_id")
        self.agent_id = int(config["agent_id"])
        self._config_cache: AgentLoadedConfig = config
        self._config_overrides = config_overrides or {}
        self.logger = logger

        # Runtime skill resolver (single source of truth for skill configs).
        # SkillService, AgentConfig and the read_skill_file tool all
        # share the same resolver instance via the factory so they observe
        # the same per-tenant cache.
        from apps.tenant_app_service.skills.resolution import get_default_skill_resolver

        self._skill_resolution = get_default_skill_resolver()

    def get_config(self) -> AgentLoadedConfig:
        """Get full agent configuration with overrides applied."""
        config = self._config_cache.copy()
        config.update(self._config_overrides)
        return config

    # === Core Identity Properties ===

    @property
    def agent_name(self) -> str:
        """Get agent name."""
        return self.get_config().get("name", f"Agent_{self.agent_id}")

    @property
    def system_prompt(self) -> str:
        """Get base system prompt."""
        return self.get_config().get("system_prompt", "")

    # === Model Settings ===

    def model_key(self) -> str | None:
        """Get model key from agent config."""
        return self.get_config().get("model_key")

    @property
    def temperature(self) -> float | None:
        """Get temperature setting."""
        return self.get_config().get("temperature")

    @property
    def top_p(self) -> float | None:
        """Get top_p setting."""
        return self.get_config().get("top_p")

    @property
    def max_tokens(self) -> int:
        """Get max tokens setting."""
        return self.get_config().get("max_tokens", 2000)

    @property
    def frequency_penalty(self) -> float | None:
        """Get frequency penalty setting."""
        return self.get_config().get("frequency_penalty")

    # === Behavior Settings ===

    @property
    def max_loop_iterations(self) -> int:
        """Get max loop iterations."""
        return self.get_config().get("max_loop_iterations", 50)

    # === System Prompt (Runtime Skill-Aware) ===

    def get_system_prompt(
        self,
        loaded_skills: list[str],
        runtime: AgentRuntimeContext,
    ) -> str:
        """Get system prompt for a specific skill.

        Args:
            loaded_skills: Loaded skill names; empty/None means base mode
            runtime: Runtime context for tenant-scoped skill resolution

        Returns:
            Combined system prompt
        """
        sections: list[str] = []

        agent_prompt = (self.system_prompt or "").strip()
        if agent_prompt:
            sections.append(agent_prompt)

        if runtime:
            available_msg = self._build_available_skills_prompt(runtime)
            if available_msg:
                sections.append(available_msg)

            normalized = self._normalize_loaded_skills(loaded_skills, runtime)
            if normalized:
                loaded_msg = self._build_loaded_skills_prompt(normalized, runtime)
                if loaded_msg:
                    sections.append(loaded_msg)

        return "\n\n".join(section for section in sections if section).strip()

    def _build_available_skills_prompt(self, runtime: AgentRuntimeContext) -> str:
        """Build an explicit Available Skills section from resolved skill metadata."""
        skills = self.get_resolved_skills_meta(runtime)
        if not skills:
            return ""

        skills_descriptions = "\n\n".join(
            f"**{skill['name']}** ({skill['scope']}):\n{skill['description']}" for skill in skills
        )
        return f"## Available Skills\n\n{skills_descriptions}".strip()

    def _build_loaded_skills_prompt(self, normalized_skills: list[str], runtime: AgentRuntimeContext) -> str:
        """Build loaded skills prompt section."""
        skill_sections: list[str] = []
        skills = self.get_resolved_skills(runtime)

        for skill_name in normalized_skills:
            skill = skills.get(skill_name)
            if not skill:
                continue
            scope_badge = f"({skill.scope.value})"
            container_path = skill.locator.container_skill_dir if skill.locator else "unknown"
            header = f"## Loaded Skill: {skill_name} {scope_badge}"
            path_hint = f"Skill directory: {container_path}/"
            prompt = skill.system_prompt or ""
            skill_sections.append(f"{header}\n\n{path_hint}\n\n{prompt}".strip())

        if not skill_sections:
            return ""
        return "# Loaded Skills\n\n" + "\n\n".join(skill_sections)

    # === Tools Configuration (Runtime Skill-Aware) ===

    def get_tools(
        self,
        loaded_skills: list[str] | None = None,
        runtime: AgentRuntimeContext | None = None,
    ) -> List[BaseTool]:
        """Get tools for loaded skills.

        Args:
            loaded_skills: Loaded skill names; empty/None means base mode
            runtime: Runtime context for tenant-scoped skill resolution

        Returns:
            List of BaseTool objects
        """
        if not loaded_skills or not runtime:
            return self._resolve_tools_from_defs(self._filter_tool_defs(self.get_effective_base_tool_defs(), runtime))

        effective_defs = self._filter_tool_defs(self._get_effective_tool_defs(loaded_skills, runtime), runtime)
        tools = self._resolve_tools_from_defs(effective_defs)

        self.logger.debug("Loaded skills %s tools: %s", loaded_skills, [t.name for t in tools])
        return tools

    def get_base_tools(self) -> List[BaseTool]:
        """Get base tools from ``default_tools`` only (no skill loaded)."""
        return self._resolve_tools_from_defs(self.get_effective_base_tool_defs())

    def get_effective_base_tool_defs(self):
        """Get resolved base-mode tool definitions from ``default_tools`` only."""
        default_tools = self.get_config().get("default_tools", [])
        defs = resolve_effective_skill_tools(
            default_tools=default_tools,
            skill_tools=[],
            tool_registry=self._get_tool_registry(),
            strict_registry=True,
        )
        return defs

    def _filter_tool_defs(self, tool_defs: list[Any], runtime: AgentRuntimeContext | None) -> list[Any]:
        if not runtime or not runtime.capability_profile or runtime.capability_profile.allowed_tool_names is None:
            return tool_defs
        allowed = set(runtime.capability_profile.allowed_tool_names)
        return [tool_def for tool_def in tool_defs if tool_def.name in allowed]

    def _get_effective_tool_defs(self, loaded_skills: list[str], runtime: AgentRuntimeContext) -> list[Any]:
        """Build effective tool definitions for base tools + loaded skills."""
        merged = self.get_effective_base_tool_defs()
        skills = self.get_resolved_skills(runtime)

        for skill_name in loaded_skills:
            skill = skills.get(skill_name)
            if not skill:
                continue
            merged = resolve_effective_skill_tools(
                default_tools=merged,
                skill_tools=skill.tools,
                tool_registry=self._get_tool_registry(),
                strict_registry=True,
            )

        return merged

    def get_tool_config(
        self, loaded_skills: list[str], tool_name: str, runtime: AgentRuntimeContext
    ) -> ToolConfig | None:
        """Get ToolConfig for a tool under loaded skills."""
        effective_defs = self._get_effective_tool_defs(loaded_skills, runtime)
        registry = self._get_tool_registry()
        for tool_def in effective_defs:
            if tool_def.name != tool_name:
                continue
            tool = registry.get(tool_name)
            if not tool:
                return None
            tool_def.tool = tool
            return tool_def
        return None

    # === Skills Metadata & Validation ===

    def has_skills(self, runtime: AgentRuntimeContext) -> bool:
        """Check if agent has skill support enabled."""
        return bool(self.get_resolved_skills(runtime))

    def get_resolved_skills(self, runtime: AgentRuntimeContext) -> Dict[str, SkillConfig]:
        """Get all resolved skills for runtime context."""
        skills = self._skill_resolution.resolve(
            tenant_id=runtime.user.tenant_id,
            user_id=runtime.user.user_id,
        )
        profile = runtime.capability_profile
        if profile and profile.allowed_skill_names is not None:
            allowed = set(profile.allowed_skill_names)
            skills = {
                name: skill
                for name, skill in skills.items()
                if name in allowed and (skill.scope is None or skill.scope.value != "personal")
            }
        return skills

    def get_resolved_skills_meta(self, runtime: AgentRuntimeContext) -> list[Dict[str, Any]]:
        """Get metadata for all resolved skills."""
        skills = self.get_resolved_skills(runtime)
        return [
            {
                "name": name,
                "description": skill.description or "",
                "scope": skill.scope.value if skill.scope else "builtin",
            }
            for name, skill in skills.items()
        ]

    def validate_load_skill(self, skill_name: str, runtime: AgentRuntimeContext) -> SkillConfig | None:
        """Validate that a skill can be loaded at runtime."""
        skills = self.get_resolved_skills(runtime)
        return skills.get(skill_name)

    def normalize_loaded_skills(self, skill_names: list[str], runtime: AgentRuntimeContext) -> list[str]:
        """Public wrapper for validating and normalizing loaded skills."""
        return self._normalize_loaded_skills(skill_names, runtime)

    def _normalize_loaded_skills(self, skill_names: list[str], runtime: AgentRuntimeContext) -> list[str]:
        """Normalize and validate loaded skill names against resolved skills."""
        if not skill_names:
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        available_skills = self.get_resolved_skills(runtime).keys()

        for skill_name in skill_names:
            if not isinstance(skill_name, str):
                continue
            candidate = skill_name.strip()
            if not candidate or candidate in seen:
                continue
            if candidate not in available_skills:
                raise ValueError(f"Skill '{candidate}' not found. Available skills: {list(available_skills)}")
            seen.add(candidate)
            normalized.append(candidate)

        return normalized

    def _get_tool_registry(self) -> dict[str, BaseTool]:
        """Lazy import of tool registry to avoid circular-import risks."""
        from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY

        return TOOL_REGISTRY

    def _resolve_tools_from_defs(self, tool_defs: list[Any]) -> list[BaseTool]:
        """Resolve tool objects from tool definitions by name."""
        registry = self._get_tool_registry()
        tools: list[BaseTool] = []
        for tool_def in tool_defs:
            tool = registry.get(tool_def.name)
            if tool:
                tools.append(tool)
            else:
                self.logger.warning("Tool not found in registry: %s", tool_def.name)
        return tools

    # === Mini Agent Specific ===

    @property
    def classification(self) -> str | None:
        """Get classification for mini agent."""
        return self.get_config().get("classification")

    @property
    def response_format(self) -> str | None:
        """Get response format for mini agent."""
        return self.get_config().get("response_format")

    # === Utility Methods ===

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get any config property by key.

        Args:
            key: Property key
            default: Default value if key not found

        Returns:
            Property value or default
        """
        return self.get_config().get(key, default)

    def __repr__(self) -> str:
        """String representation."""
        return f"AgentConfig(agent_id={self.agent_id}, agent_name={self.agent_name})"
