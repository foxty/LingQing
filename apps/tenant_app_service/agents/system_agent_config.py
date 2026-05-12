"""Unified configuration for all system agents and mini agents.

Hybrid Configuration Approach:
1. **Technical Config (Python)**: Tools, capabilities, response_format
   - Type-safe, IDE support, direct object references
2. **Business Config (YAML)**: Prompts, parameters, descriptions
   - Easy to modify, hot-reload capable, non-developer friendly

Design:
- YAML file (config/agents.yaml) contains prompts and parameters
- Python file defines tool/capability registries and response formats
- Loader merges both sources to create final AgentConfig/MiniAgentConfig
"""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any, Dict

import yaml
from langchain_core.tools import BaseTool

import apps.tenant_app_service.agents.tools as tools_package
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import AgentLoadedConfig
from apps.tenant_app_service.agents.mini.domain import (
    Classification,
    MiniAgentConfig,
    TableMetadata,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


# ============================================================================
# Technical Configuration Registries (Python)
# ============================================================================


def _is_tool_return_contract_compliant(tool: BaseTool) -> bool:
    """Check tool return annotation contract.

    Contract: decorated tool callable must annotate return type as ToolResult.
    """
    callable_obj = getattr(tool, "coroutine", None) or getattr(tool, "func", None)
    if callable_obj is None:
        return False

    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False

    annotation = signature.return_annotation
    if annotation is inspect.Signature.empty:
        return False

    if annotation is ToolResult:
        return True

    # Support string forward references: "ToolResult"
    if isinstance(annotation, str):
        return annotation == "ToolResult"

    return False


def _discover_tool_registry() -> Dict[str, BaseTool]:
    """Discover tool objects from modules under the tools package.

    Only LangChain tools (objects created by @tool) are registered.
    """
    registry: Dict[str, BaseTool] = {}
    invalid_tools: list[str] = []

    modules = sorted(
        pkgutil.iter_modules(tools_package.__path__, prefix=f"{tools_package.__name__}."),
        key=lambda module_info: module_info.name,
    )
    for module_info in modules:
        try:
            module = importlib.import_module(module_info.name)
        except Exception:
            logger.exception("Failed to import tools module '%s' during registry discovery", module_info.name)
            continue

        for attr_name, attr_value in vars(module).items():
            if not isinstance(attr_value, BaseTool):
                continue

            tool_name = attr_value.name or attr_name

            if not _is_tool_return_contract_compliant(attr_value):
                invalid_tools.append(f"{tool_name} ({module_info.name}.{attr_name})")
                continue

            if tool_name in registry:
                # Keep first match to avoid non-deterministic collisions.
                if registry[tool_name] is not attr_value:
                    logger.warning(
                        "Duplicate tool name '%s' found in '%s'; keeping first discovered instance",
                        tool_name,
                        module_info.name,
                    )
                continue

            registry[tool_name] = attr_value

    if invalid_tools:
        invalid_tools_sorted = sorted(set(invalid_tools))
        raise RuntimeError(
            "Detected non-compliant tools that do not return ToolResult: " + ", ".join(invalid_tools_sorted)
        )

    discovered_tool_names = sorted(registry)
    logger.info(
        "Discovered %d tools from package '%s': %s",
        len(discovered_tool_names),
        tools_package.__name__,
        discovered_tool_names,
    )
    return registry


# Tool Registry: Maps tool names to actual Tool objects (without limits)
# Limits are defined in YAML config per agent
TOOL_REGISTRY = _discover_tool_registry()

# Response Format Registry: Maps schema names to Pydantic classes
RESPONSE_FORMAT_REGISTRY = {
    "TableMetadata": TableMetadata,
    "Classification": Classification,
}


# ============================================================================
# Configuration Loader (Merges YAML + Python)
# ============================================================================


class AgentConfigLoader:
    """Loads and merges YAML business config with Python technical config.

    Supports hot-reload of YAML config without restarting the service.
    """

    def __init__(self, config_path: str = "config/agents.yaml"):
        """Initialize loader.

        Args:
            config_path: Path to YAML config file (relative to project root)
        """
        self.config_path = Path(config_path)
        self._yaml_config: Dict[str, Any] | None = None
        self.logger = logger

    def load_yaml(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load YAML config with caching.

        Args:
            force_reload: If True, reload from disk even if cached

        Returns:
            Parsed YAML config dict
        """
        if self._yaml_config is None or force_reload:
            try:
                with open(self.config_path) as f:
                    self._yaml_config = yaml.safe_load(f)
                self._validate_config(self._yaml_config)
            except FileNotFoundError:
                self.logger.error(f"Config file not found: {self.config_path}")
                self._yaml_config = {"system_agents": {}, "mini_agents": {}}
            except yaml.YAMLError as e:
                self.logger.error(f"Failed to parse YAML config: {e}")
                self._yaml_config = {"system_agents": {}, "mini_agents": {}}

        return self._yaml_config

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate config for uniqueness of names and IDs.

        Args:
            config: Parsed YAML config

        Raises:
            ValueError: If duplicate names or IDs found
        """
        # Check system agents
        agent_ids = set()
        agent_names = set()
        for agent_key, agent_def in config.get("system_agents", {}).items():
            agent_id = agent_def.get("agent_id")
            agent_name = agent_def.get("name")

            if agent_id in agent_ids:
                raise ValueError(f"Duplicate agent_id: {agent_id}")
            if agent_name in agent_names:
                raise ValueError(f"Duplicate agent name: {agent_name}")

            agent_ids.add(agent_id)
            agent_names.add(agent_name)

        # Check mini agents
        mini_ids = set()
        mini_names = set()
        for preset_name, preset_def in config.get("mini_agents", {}).items():
            preset_id = preset_def.get("agent_id")
            preset_agent_name = preset_def.get("agent_name")

            if preset_id in mini_ids or preset_id in agent_ids:
                raise ValueError(f"Duplicate agent_id: {preset_id}")
            if preset_agent_name in mini_names or preset_agent_name in agent_names:
                raise ValueError(f"Duplicate agent_name: {preset_agent_name}")

            mini_ids.add(preset_id)
            mini_names.add(preset_agent_name)

        # Check that all referenced skills have either a legacy YAML file or
        # a standard skill directory (with SKILL.md) at init time.
        self._validate_skill_references(config)

    def _validate_skill_references(self, config: Dict[str, Any]) -> None:
        """Validate that referenced skills exist under the sibling ``skills`` directory."""
        skills_dir = self.config_path.parent / "skills"

        for agent_key, agent_def in config.get("system_agents", {}).items():
            skill_names = self._extract_skill_names(agent_key, agent_def.get("skills", {}))
            for skill_name in skill_names:
                if self._skill_file_exists(skills_dir, skill_name):
                    continue
                expected_yaml = skills_dir / f"{skill_name}.yaml"
                expected_yml = skills_dir / f"{skill_name}.yml"
                expected_dir = skills_dir / skill_name / "SKILL.md"
                raise ValueError(
                    f"System agent '{agent_key}' references missing skill '{skill_name}'. "
                    f"Expected skill file at '{expected_yaml}' or '{expected_yml}', "
                    f"or standard skill file at '{expected_dir}'."
                )

    def _extract_skill_names(self, agent_key: str, skills_field: Any) -> set[str]:
        """Extract skill names from skills config field.

        Supported format:
        - list: skill names
        """
        if not skills_field:
            return set()

        if isinstance(skills_field, list):
            skill_names = set()
            for idx, skill_name in enumerate(skills_field):
                if not isinstance(skill_name, str) or not skill_name.strip():
                    raise ValueError(
                        f"System agent '{agent_key}' field 'skills' list entry #{idx} must be non-empty string"
                    )
                normalized = skill_name.strip()
                if normalized in skill_names:
                    raise ValueError(f"System agent '{agent_key}' has duplicate skill '{normalized}' in 'skills' list")
                skill_names.add(normalized)
            return skill_names

        raise ValueError(f"System agent '{agent_key}' field 'skills' must be a list of skill names")

    @staticmethod
    def _skill_file_exists(skills_dir: Path, skill_name: str) -> bool:
        """Check whether a legacy or standard skill exists for the given name."""
        yaml_path = skills_dir / f"{skill_name}.yaml"
        yml_path = skills_dir / f"{skill_name}.yml"
        standard_skill_file = skills_dir / skill_name / "SKILL.md"
        return yaml_path.exists() or yml_path.exists() or standard_skill_file.exists()

    def reload_yaml(self) -> Dict[str, Any]:
        """Force reload YAML config from disk.

        Returns:
            Reloaded YAML config dict
        """
        return self.load_yaml(force_reload=True)

    def get_system_agent_config(self, agent_id: int) -> AgentLoadedConfig | None:
        """Get system agent config by ID from YAML.

        Args:
            agent_id: System agent ID

        Returns:
            Agent config dict or None if not found
        """
        yaml_config = self.load_yaml()
        for agent_key, agent_def in yaml_config.get("system_agents", {}).items():
            if agent_def.get("agent_id") == agent_id:
                return agent_def
        return None

    def get_system_agent_config_by_name(self, agent_name: str) -> AgentLoadedConfig | None:
        """Get system agent config by name from YAML.

        Args:
            agent_name: System agent name

        Returns:
            Agent config dict or None if not found
        """
        yaml_config = self.load_yaml()
        for agent_key, agent_def in yaml_config.get("system_agents", {}).items():
            if agent_def.get("name") == agent_name:
                return agent_def
        return None

    def get_mini_agent_config(self, agent_id: int) -> Dict[str, Any] | None:
        """Get mini agent config by ID from YAML.

        Args:
            agent_id: Mini agent ID

        Returns:
            Mini agent config dict or None if not found
        """
        yaml_config = self.load_yaml()
        for preset_name, preset_def in yaml_config.get("mini_agents", {}).items():
            if preset_def.get("agent_id") == agent_id:
                return preset_def
        return None

    def get_mini_agent_config_by_name(self, agent_name: str) -> Dict[str, Any] | None:
        """Get mini agent config by name from YAML.

        Args:
            agent_name: Mini agent name

        Returns:
            Mini agent config dict or None if not found
        """
        yaml_config = self.load_yaml()
        for preset_name, preset_def in yaml_config.get("mini_agents", {}).items():
            if preset_def.get("agent_name") == agent_name:
                return preset_def
        return None

    def create_mini_agent_config(
        self,
        agent_id: int | None = None,
        agent_name: str | None = None,
        model_key: str | None = None,
    ) -> MiniAgentConfig:
        """Create MiniAgentConfig by merging YAML + Python configs.

        Args:
            agent_id: Mini agent ID (optional if agent_name provided)
            agent_name: Mini agent name (optional if agent_id provided)
            model_key: Optional model key override (rarely needed)

        Returns:
            MiniAgentConfig instance

        Raises:
            ValueError: If neither agent_id nor agent_name provided, or agent not found
        """
        if agent_id is None and agent_name is None:
            raise ValueError("Either agent_id or agent_name must be provided")

        if agent_name:
            preset = self.get_mini_agent_config_by_name(agent_name)
            if not preset:
                raise ValueError(f"Mini agent not found with name: {agent_name}")
        else:
            preset = self.get_mini_agent_config(agent_id)
            if not preset:
                raise ValueError(f"Mini agent not found with ID: {agent_id}")

        # Resolve response_format from registry
        response_format = None
        response_format_ref = preset.get("response_format_ref")
        if response_format_ref and response_format_ref in RESPONSE_FORMAT_REGISTRY:
            response_format = RESPONSE_FORMAT_REGISTRY[response_format_ref]

        # All config from YAML, model_key override only when necessary
        final_model_key = model_key or preset.get("model_key")

        return MiniAgentConfig(
            agent_id=preset["agent_id"],
            agent_name=preset["agent_name"],
            system_prompt=preset["system_prompt"],
            model_key=final_model_key,
            temperature=preset.get("temperature"),
            max_tokens=preset.get("max_tokens"),
            response_format=response_format,
        )


# Global loader instance
_config_loader: AgentConfigLoader | None = None


def get_config_loader() -> AgentConfigLoader:
    """Get global config loader instance (singleton)."""
    global _config_loader
    if _config_loader is None:
        _config_loader = AgentConfigLoader()
    return _config_loader


def load_yaml_agent_config(
    agent_id: int,
    *,
    config_loader: AgentConfigLoader | None = None,
) -> AgentLoadedConfig:
    """Load a system or mini agent document from YAML by ``agent_id``.

    Call sites (chat, tests) resolve config here. ``AgentBase`` / ``AgentConfig``
    only consume the returned document.
    """
    loader = config_loader or get_config_loader()
    yaml_config = loader.load_yaml()
    system_agents = yaml_config.get("system_agents") or {}
    mini_agents = yaml_config.get("mini_agents") or {}
    for agent_def in system_agents.values():
        if isinstance(agent_def, dict) and agent_def.get("agent_id") == agent_id:
            return agent_def
    for preset_def in mini_agents.values():
        if isinstance(preset_def, dict) and preset_def.get("agent_id") == agent_id:
            return preset_def
    raise ValueError(
        f"Agent ID {agent_id} not found in config. "
        f"Available system agents: {list(system_agents.keys())}, "
        f"mini agents: {list(mini_agents.keys())}"
    )


__all__ = [
    "get_config_loader",
    "load_yaml_agent_config",
]
