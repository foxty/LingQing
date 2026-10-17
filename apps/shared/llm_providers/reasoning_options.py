"""Normalize and read thinking_effort_options from profile reasoning_config snapshots."""

from __future__ import annotations

from typing import Any, TypedDict


class ThinkingEffortOption(TypedDict):
    name: str
    value: str


def normalize_thinking_effort_options(raw: object) -> list[ThinkingEffortOption] | None:
    """Catalog/DB: string or {name?, value} entries; name defaults to value."""
    if not isinstance(raw, list) or not raw:
        return None
    options: list[ThinkingEffortOption] = []
    for item in raw:
        if isinstance(item, str):
            value = item.strip()
            if value:
                options.append({"name": value, "value": value})
            continue
        if isinstance(item, dict):
            wire = item.get("value")
            if wire is None:
                continue
            value = str(wire).strip()
            if not value:
                continue
            label = item.get("name")
            name = str(label).strip() if label is not None and str(label).strip() else value
            options.append({"name": name, "value": value})
    return options or None


def thinking_effort_options_from_reasoning_config(reasoning: dict[str, Any] | None) -> list[ThinkingEffortOption]:
    if not reasoning:
        return []
    return normalize_thinking_effort_options(reasoning.get("thinking_effort_options")) or []


def default_thinking_effort_value(options: list[ThinkingEffortOption]) -> str:
    if not options:
        return ""
    return options[0]["value"]
