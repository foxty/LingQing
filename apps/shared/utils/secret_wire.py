"""Wire + display contract for sensitive values on integration APIs.

PATCH / merge (``is_unchanged_secret_on_wire``)
  Preserve stored secret only when the client sends ``null`` or blank/whitespace.
  Prefer **omitting** the key entirely (portal ``secretPayloadValue``).

GET display
  ``mask_secret_for_display`` for optional previews in JSON; stored paths on ``masked_fields``.

``is_display_mask``
  Detects echoed partial masks in custom JSON submit sanitizer (portal only — not merge).

``API_SECRET_PLACEHOLDER``
  Legacy/corrupt stored config only (e.g. catalog sync parse) — not emitted on public GET.

Keep ``FieldCipher`` for encrypt/decrypt only.
"""

from __future__ import annotations

from typing import Any

# Not used on public GET responses (use ``masked_fields``). Guards internal/legacy config blobs.
API_SECRET_PLACEHOLDER = "***"


def mask_secret_for_display(value: str) -> str:
    """Partial mask for API responses (e.g. ``sk****ey``)."""
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def is_display_mask(value: str) -> bool:
    """True for partial masks from ``mask_secret_for_display`` (not ``***`` placeholder)."""
    if not value or value == API_SECRET_PLACEHOLDER:
        return False
    if len(value) <= 4:
        return all(ch == "*" for ch in value)
    if value.startswith("*"):
        return False
    middle = value[2:-2]
    if len(middle) < 1:
        return False
    return all(ch == "*" for ch in middle)


def is_unchanged_secret_on_wire(value: Any) -> bool:
    """Merge rule: unchanged only when null or empty string (omit keys on update when possible)."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return not value.strip()


# Backward-compatible alias used in merge helpers and tests.
is_preserve_secret_value = is_unchanged_secret_on_wire

