"""Scenario helpers: redact GET payloads and build ``masked_fields`` from declared specs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecretLeafSpec:
    """One stored secret on a GET resource (root-relative path + key path in the config object)."""

    response_path: str
    leaf_path: tuple[str, ...]


def config_has_secret_value(raw: Any) -> bool:
    return isinstance(raw, str) and bool(raw.strip())


def get_config_leaf(config: dict[str, Any], leaf_path: tuple[str, ...]) -> Any:
    node: Any = config
    for key in leaf_path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def set_config_leaf(config: dict[str, Any], leaf_path: tuple[str, ...], value: str | None) -> None:
    if not leaf_path:
        return
    if len(leaf_path) == 1:
        key = leaf_path[0]
        if value is None:
            config.pop(key, None)
        else:
            config[key] = value
        return
    parent = config
    for key in leaf_path[:-1]:
        child = parent.get(key)
        if not isinstance(child, dict):
            return
        parent = child
    last = leaf_path[-1]
    if value is None:
        parent.pop(last, None)
    else:
        parent[last] = value


def redact_secret_leaves_for_get(
    config: dict[str, Any],
    specs: Sequence[SecretLeafSpec],
    *,
    mask_value: Callable[[Any], str | None],
) -> tuple[dict[str, Any], list[str]]:
    """Apply GET redaction: optional preview per spec; always list path when a secret is stored."""
    out = deepcopy(config)
    masked_fields: list[str] = []
    for spec in specs:
        raw = get_config_leaf(out, spec.leaf_path)
        if not config_has_secret_value(raw):
            continue
        masked_fields.append(spec.response_path)
        set_config_leaf(out, spec.leaf_path, mask_value(raw))
    masked_fields.sort()
    return out, masked_fields


def collect_stored_secret_paths(
    payload: Any,
    *,
    root_prefix: str,
    sensitive_leaf_keys: frozenset[str],
) -> list[str]:
    """Build ``masked_fields`` from plaintext config (before mask), including nested dicts."""
    paths: list[str] = []

    def join(prefix: str, key: str) -> str:
        return f"{prefix}.{key}" if prefix else key

    def walk(node: Any, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            path = join(prefix, key)
            if isinstance(value, dict):
                walk(value, path)
            elif key in sensitive_leaf_keys and config_has_secret_value(value):
                paths.append(path)

    walk(payload, root_prefix)
    paths.sort()
    return paths