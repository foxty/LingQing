"""Payload sanitization for audit events (defense in depth after typed builders)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# PRD-allowed metadata keys (booleans, field name lists) — never strip by pattern rules.
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

_SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "bot_token",
        "signing_secret",
        "api_key",
        "apikey",
        "credentials",
        "credential",
        "secret",
        "client_secret",
    }
)

_SECRET_KEY_SUFFIXES = ("_token", "_secret", "_password", "_api_key")
_SECRET_KEY_PREFIXES = ("api_key", "apikey", "token")

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
    if key_l in _SECRET_KEYS:
        return True
    if key_l.endswith(_SECRET_KEY_SUFFIXES) or key_l.startswith(_SECRET_KEY_PREFIXES):
        return True
    return _SENSITIVE_KEY_RE.search(key_l) is not None


def _sanitize_nested_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return sanitize_audit_payload(value) or {}
    if isinstance(value, list):
        return [_sanitize_nested_value(item) for item in value]
    return value


def sanitize_audit_payload(payload: Mapping[str, Any] | None) -> dict | None:
    """Strip known secret **value** keys before persistence."""
    if payload is None:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if _should_drop_key(key):
            continue
        cleaned[key] = _sanitize_nested_value(value)
    return cleaned or {}