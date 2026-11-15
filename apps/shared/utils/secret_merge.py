"""Merge client payloads with stored secrets (BYOT / integration credentials).

Contract (update & saved-resource tests):
- Sensitive key omitted, None, or empty/whitespace string → keep stored.
- Any other non-empty string → replace stored (do not send ``***`` or GET masks).

Create flows must validate required secrets before calling merge (merge does not invent secrets).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.secret_wire import (
    API_SECRET_PLACEHOLDER,
    is_unchanged_secret_on_wire,
)

__all__ = [
    "API_SECRET_PLACEHOLDER",
    "is_preserve_secret_value",
    "merge_dict_preserve_secrets",
    "merge_secret_value",
]


def is_preserve_secret_value(value: Any) -> bool:
    """True when the client did not supply a new secret."""
    return is_unchanged_secret_on_wire(value)


def merge_secret_value(existing: Any, incoming: Any) -> Any:
    """Pick stored or incoming for one sensitive scalar."""
    if is_unchanged_secret_on_wire(incoming):
        return existing
    return incoming


def merge_dict_preserve_secrets(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
    sensitive_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Shallow merge with preserve semantics on sensitive keys; recurse into nested dicts."""
    base = deepcopy(existing or {})
    if not incoming:
        return base

    keys = sensitive_keys if sensitive_keys is not None else INTEGRATION_SECRET_LEAF_KEYS
    merged = {**base, **incoming}

    for key, new_value in incoming.items():
        if key in keys:
            merged[key] = merge_secret_value(base.get(key), new_value)
        elif isinstance(new_value, dict) and isinstance(base.get(key), dict):
            merged[key] = merge_dict_preserve_secrets(base.get(key), new_value, keys)
        else:
            merged[key] = new_value

    return merged