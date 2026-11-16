"""Payload sanitization for audit events (PRD §5.2)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# PRD-allowed metadata keys (booleans, field name lists) — never strip by substring rules.
_ALLOWED_METADATA_KEYS = frozenset(
    {
        "credentials_changed",
        "credential_field_names",
        "credentials_present",
        "fields_changed",
        "env_var_keys_changed",
        "change_summary",
        "filter_summary",
        "exported_count",
        "truncated",
        "total_matched",
    }
)

_BLOCKED_VALUE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "bot_token",
        "signing_secret",
        "api_key",
        "credentials",
        "credential",
    }
)

# Secret **value** keys only — do not match substrings like "credentials_present".
_SENSITIVE_KEY_RE = re.compile(
    r"(^password$|^passwd$|_token$|^token$|^secret$|api_key|apikey|^bot_token$|^signing_secret$)",
    re.IGNORECASE,
)


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    visible = local[0]
    return f"{visible}***@{domain}"


def _should_drop_key(key: str) -> bool:
    key_l = key.lower()
    if key_l in _ALLOWED_METADATA_KEYS:
        return False
    if key_l in _BLOCKED_VALUE_KEYS:
        return True
    return _SENSITIVE_KEY_RE.search(key_l) is not None


def sanitize_audit_payload(payload: Mapping[str, Any] | None) -> dict | None:
    """Strip secret-bearing keys/values from audit payload before persistence."""
    if payload is None:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if _should_drop_key(key):
            continue
        if isinstance(value, Mapping):
            nested = sanitize_audit_payload(value)
            if nested:
                cleaned[key] = nested
            continue
        if isinstance(value, list):
            cleaned[key] = [
                sanitize_audit_payload(item) if isinstance(item, Mapping) else item for item in value
            ]
            continue
        cleaned[key] = value
    return cleaned or {}