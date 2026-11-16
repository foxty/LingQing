import pytest

from apps.tenant_app_service.auth.domain import UserPreferences
from apps.tenant_app_service.auth.user_display_preferences import (
    ALLOWED_DATETIME_FORMATS,
    DEFAULT_DATETIME_FORMAT,
    normalize_datetime_format,
)

# Keep in sync with apps/tenant_app_portal/src/lib/datetimeFormats.ts DATETIME_FORMAT_IDS
PORTAL_DATETIME_FORMAT_IDS = frozenset(
    {
        "locale",
        "ymd_hms_24",
        "ymd_hms_12",
        "ymd",
        "mdy_hm_12",
    }
)


def test_allowed_datetime_formats_match_portal_ids():
    assert ALLOWED_DATETIME_FORMATS == PORTAL_DATETIME_FORMAT_IDS
    assert DEFAULT_DATETIME_FORMAT == "locale"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ymd_hms_24", "ymd_hms_24"),
        ("  ymd  ", "ymd"),
        ("iso_8601", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_normalize_datetime_format(raw: object, expected: str | None):
    assert normalize_datetime_format(raw) == expected


def test_user_preferences_from_raw_parses_display_fields():
    prefs = UserPreferences.from_raw(
        {"timezone_iana": "Asia/Shanghai", "datetime_format": "ymd_hms_24"}
    )
    assert prefs.timezone_iana == "Asia/Shanghai"
    assert prefs.datetime_format == "ymd_hms_24"


def test_user_preferences_from_raw_strips_invalid_datetime_format():
    prefs = UserPreferences.from_raw(
        {"timezone_iana": "UTC", "datetime_format": "not-a-format", "other": "kept"}
    )
    assert prefs.timezone_iana == "UTC"
    assert prefs.datetime_format is None


def test_user_preferences_from_raw_non_dict():
    assert UserPreferences.from_raw(None) == UserPreferences()
    assert UserPreferences.from_raw("json") == UserPreferences()