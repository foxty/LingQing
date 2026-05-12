"""Tool-list merge helper for skill-enabled agent runtime.

This module is the agent-layer complement to
:class:`apps.tenant_app_service.skills.resolution.SkillResolver`. While the
resolver owns skill *config* loading and per-tenant precedence merging, this
module owns the *tool-list* merge logic: combining ``default_tools`` with
the ``tools`` declared on each loaded skill into a single deduplicated
``ToolConfig`` list.

Renamed from ``resolver.py`` to ``tool_resolver.py`` as part of the
consolidation so its responsibility (tool list, not skill resolution) is
clear. ``agents.skills.resolver.resolve_effective_skill_tools`` remains
importable as a back-compat alias.
"""

from __future__ import annotations

from typing import Any

from apps.tenant_app_service.agents.domain import RETENTION_TRANSIENT, TOOL_LIMIT_UNLIMITED, ToolConfig


def resolve_effective_skill_tools(
    default_tools: list[ToolConfig | dict[str, Any] | str] | None,
    skill_tools: list[ToolConfig | dict[str, Any] | str] | None,
    tool_registry: dict[str, Any] | None = None,
    strict_registry: bool = False,
) -> list[ToolConfig]:
    """Merge default tools and skill tools into one effective tool list.

    Rules:
    - Preserve first-seen order (default first, then skill additions).
    - Deduplicate by tool name.
    - If duplicated, apply stricter limit (min wins; ``inf`` = unlimited).
    - If ``tool_registry`` is provided:
      - ``strict_registry=True``: raise ValueError on unknown tool.
      - ``strict_registry=False``: silently skip unknown tools.
    """
    merged: dict[str, ToolConfig] = {}
    ordered_names: list[str] = []

    for tool in _normalize_tool_defs(default_tools):
        if not _is_tool_allowed(tool.name, tool_registry, strict_registry):
            continue
        merged[tool.name] = tool
        ordered_names.append(tool.name)

    for tool in _normalize_tool_defs(skill_tools):
        if not _is_tool_allowed(tool.name, tool_registry, strict_registry):
            continue

        if tool.name not in merged:
            merged[tool.name] = tool
            ordered_names.append(tool.name)
            continue

        existing = merged[tool.name]
        merged[tool.name] = ToolConfig(
            name=tool.name,
            limit=_merge_limit(existing.limit, tool.limit),
            hitl=existing.hitl if existing.hitl else tool.hitl,
            result_retention=tool.result_retention
            if tool.result_retention != RETENTION_TRANSIENT
            else existing.result_retention,
            cacheable=existing.cacheable or tool.cacheable,
            cache_invalidates=list(set(existing.cache_invalidates + tool.cache_invalidates)),
        )

    return [merged[name] for name in ordered_names]


def _normalize_tool_defs(
    tool_defs: list[ToolConfig | dict[str, Any] | str] | None,
) -> list[ToolConfig]:
    """Normalize mixed tool definitions to ``ToolConfig`` list."""
    if not tool_defs:
        return []

    normalized: list[ToolConfig] = []
    for idx, tool_def in enumerate(tool_defs):
        if isinstance(tool_def, ToolConfig):
            normalized.append(tool_def)
            continue

        if isinstance(tool_def, str):
            if not tool_def.strip():
                raise ValueError(f"Tool entry #{idx} must not be empty")
            normalized.append(ToolConfig(name=tool_def))
            continue

        if isinstance(tool_def, dict):
            tool_name = tool_def.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError(f"Tool entry #{idx} must define non-empty string field 'name'")

            raw_limit = tool_def.get("limit", 0)
            if not isinstance(raw_limit, int) or raw_limit < 0:
                raise ValueError(f"Tool '{tool_name}' field 'limit' must be integer >= 0")
            limit = raw_limit or TOOL_LIMIT_UNLIMITED

            hitl = tool_def.get("hitl", {})
            if not isinstance(hitl, dict):
                raise ValueError(f"Tool '{tool_name}' field 'hitl' must be an object")

            result_retention = tool_def.get("result_retention", RETENTION_TRANSIENT)
            cacheable = tool_def.get("cacheable", False)
            cache_invalidates = tool_def.get("cache_invalidates", [])
            normalized.append(
                ToolConfig(
                    name=tool_name,
                    limit=limit,
                    hitl=hitl,
                    result_retention=result_retention,
                    cacheable=cacheable,
                    cache_invalidates=cache_invalidates,
                )
            )
            continue

        raise ValueError(f"Tool entry #{idx} has unsupported type: {type(tool_def)}")

    return normalized


def _merge_limit(existing: int, incoming: int) -> int:
    """Merge limits — stricter (smaller) wins."""
    return min(existing, incoming)


def _is_tool_allowed(
    tool_name: str,
    tool_registry: dict[str, Any] | None,
    strict_registry: bool,
) -> bool:
    if tool_registry is None:
        return True
    if tool_name in tool_registry:
        return True
    if strict_registry:
        raise ValueError(f"Unknown tool '{tool_name}' in resolver")
    return False
