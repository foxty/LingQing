import pytest
from pydantic import ValidationError

from apps.tenant_app_service.auth.schemas import UpdateProfilePreferencesRequest


def test_update_profile_preferences_accepts_valid_timezone():
    payload = UpdateProfilePreferencesRequest(timezone_iana="Asia/Shanghai")
    assert payload.timezone_iana == "Asia/Shanghai"


def test_update_profile_preferences_rejects_invalid_timezone():
    with pytest.raises(ValidationError):
        UpdateProfilePreferencesRequest(timezone_iana="Invalid/Timezone")


def test_update_profile_preferences_accepts_valid_datetime_format():
    payload = UpdateProfilePreferencesRequest(datetime_format="ymd_hms_24")
    assert payload.datetime_format == "ymd_hms_24"


def test_update_profile_preferences_rejects_invalid_datetime_format():
    with pytest.raises(ValidationError):
        UpdateProfilePreferencesRequest(datetime_format="iso_8601")


def test_update_profile_preferences_patch_excludes_unset_fields():
    payload = UpdateProfilePreferencesRequest(timezone_iana="UTC")
    assert payload.model_dump(exclude_unset=True) == {"timezone_iana": "UTC"}
