"""Platform tool catalog: default policy specs merged with the Python tool registry."""

from __future__ import annotations

from typing import Any

from apps.tenant_app_service.agents.domain import TOOL_LIMIT_UNLIMITED, AgentToolYaml, ToolConfig


def build_platform_tool_specs(
    raw_specs: dict[str, Any] | None,
    registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Merge YAML policy entries with every registered tool (missing tools default to {})."""
    if raw_specs is None:
        raw_specs = {}
    unknown = set(raw_specs.keys()) - set(registry.keys())
    if unknown:
        raise ValueError(f"platform.tool_specs references unknown tools: {sorted(unknown)}")

    merged: dict[str, dict[str, Any]] = {name: {} for name in registry}
    for name, spec in raw_specs.items():
        if spec is None:
            merged[name] = {}
        elif isinstance(spec, dict):
            merged[name] = dict(spec)
        else:
            raise ValueError(f"platform.tool_specs.{name} must be a mapping")
    return merged


def validate_platform_tool_specs(
    specs: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    *,
    strict_full_catalog: bool,
) -> None:
    """Ensure specs cover the registry when strict_full_catalog is enabled."""
    if not strict_full_catalog:
        return
    registry_names = set(registry.keys())
    spec_names = set(specs.keys())
    missing = registry_names - spec_names
    extra = spec_names - registry_names
    if missing:
        raise ValueError(f"platform.tool_specs missing registry tools: {sorted(missing)}")
    if extra:
        raise ValueError(f"platform.tool_specs unknown tools: {sorted(extra)}")


def _tool_entry_name(entry: str | dict[str, Any]) -> str:
    if isinstance(entry, str):
        name = entry.strip()
        if not name:
            raise ValueError("default_tools entry must not be empty")
        return name
    if isinstance(entry, dict):
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("default_tools dict entry requires non-empty 'name'")
        return name.strip()
    raise ValueError(f"Unsupported default_tools entry type: {type(entry)}")


def resolve_tool_defs(
    tool_entries: list[str | dict[str, Any]],
    platform_specs: dict[str, dict[str, Any]],
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> list[AgentToolYaml]:
    """Build agent ``default_tools`` from names and/or dicts using platform policy defaults."""
    overrides = overrides or {}
    result: list[AgentToolYaml] = []
    seen: set[str] = set()

    for entry in tool_entries:
        name = _tool_entry_name(entry)
        if name in seen:
            continue
        seen.add(name)

        base = dict(platform_specs.get(name, {}))
        if isinstance(entry, dict):
            for key, value in entry.items():
                if key != "name":
                    base[key] = value
        if name in overrides:
            base.update(overrides[name])

        tool_def: AgentToolYaml = {"name": name}
        tool_def.update(base)  # type: ignore[typeddict-item]
        result.append(tool_def)

    return result


def skill_tool_configs_to_agent_tool_yaml(
    tools: list[ToolConfig],
    platform_specs: dict[str, dict[str, Any]],
) -> list[AgentToolYaml]:
    """Apply platform default policy to skill-declared tools; skill fields override platform."""
    if not tools:
        return []
    overrides: dict[str, dict[str, Any]] = {}
    for tool in tools:
        override: dict[str, Any] = {
            "hitl": tool.hitl,
            "result_retention": tool.result_retention,
            "cacheable": tool.cacheable,
            "cache_invalidates": list(tool.cache_invalidates),
        }
        if tool.limit != TOOL_LIMIT_UNLIMITED:
            override["limit"] = tool.limit
        overrides[tool.name] = override
    names = [tool.name for tool in tools]
    return resolve_tool_defs(names, platform_specs, overrides=overrides)


def extract_default_tool_names(default_tools: list[Any] | None) -> list[str]:
    """Normalize ``default_tools`` field to ordered unique tool names."""
    if not default_tools:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for entry in default_tools:
        name = _tool_entry_name(entry)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
