"""Payload sanitization for audit events (defense in depth after typed builders)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Exact key names whose values must never be stored (values may still carry secrets).
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


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    visible = local[0]
    return f"{visible}***@{domain}"


def _should_drop_key(key: str) -> bool:
    return key.lower() in _SECRET_KEYS


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