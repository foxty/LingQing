"""Payload sanitization for audit events (PRD §5.2)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|token|secret|api_key|apikey|credential|bot_token|signing_secret)",
    re.IGNORECASE,
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


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    visible = local[0]
    return f"{visible}***@{domain}"


def sanitize_audit_payload(payload: Mapping[str, Any] | None) -> dict | None:
    """Strip secret-bearing keys/values from audit payload before persistence."""
    if payload is None:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        key_l = key.lower()
        if key_l in _BLOCKED_VALUE_KEYS or _SENSITIVE_KEY_RE.search(key):
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