"""Allowed portal display preset IDs for users.preferences.datetime_format (not ISO/strftime)."""

from __future__ import annotations

from typing import Final

ALLOWED_DATETIME_FORMATS: Final[frozenset[str]] = frozenset(
    {
        "locale",
        "ymd_hms_24",
        "ymd_hms_12",
        "ymd",
        "mdy_hm_12",
    }
)

DEFAULT_DATETIME_FORMAT: Final[str] = "locale"


def normalize_datetime_format(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate in ALLOWED_DATETIME_FORMATS:
        return candidate
    return None