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


def default_thinking_effort_value(
    options: list[ThinkingEffortOption],
    *,
    explicit_default: str | None = None,
) -> str:
    if not options:
        return ""
    if explicit_default is not None:
        wire = str(explicit_default).strip()
        allowed = {opt["value"] for opt in options}
        if wire in allowed:
            return wire
    return options[0]["value"]


def default_thinking_effort_from_reasoning_config(reasoning: dict[str, Any] | None) -> str:
    """Profile default for channels without per-turn effort (Slack, scheduler, etc.)."""
    options = thinking_effort_options_from_reasoning_config(reasoning)
    explicit = reasoning.get("default_thinking_effort") if reasoning else None
    explicit_wire = str(explicit).strip() if explicit is not None else None
    return default_thinking_effort_value(
        options,
        explicit_default=explicit_wire or None,
    )


def normalize_reasoning_config(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Persisted reasoning_config: normalized options and validated default."""
    if raw is None:
        return None
    config = dict(raw)
    if config.get("supports_thinking") is not True:
        config["supports_thinking"] = False
        config["thinking_effort_options"] = []
        config.pop("default_thinking_effort", None)
        return config

    options = normalize_thinking_effort_options(config.get("thinking_effort_options")) or []
    config["thinking_effort_options"] = options
    explicit = config.get("default_thinking_effort")
    if explicit is not None:
        wire = str(explicit).strip()
        allowed = {opt["value"] for opt in options}
        if wire and wire in allowed:
            config["default_thinking_effort"] = wire
        else:
            config.pop("default_thinking_effort", None)
    return config
