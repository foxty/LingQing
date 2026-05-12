import pytest
from pydantic import ValidationError

from apps.tenant_app_service.auth.schemas import UpdateProfilePreferencesRequest


def test_update_profile_preferences_accepts_valid_timezone():
    payload = UpdateProfilePreferencesRequest(timezone_iana="Asia/Shanghai")
    assert payload.timezone_iana == "Asia/Shanghai"


def test_update_profile_preferences_rejects_invalid_timezone():
    with pytest.raises(ValidationError):
        UpdateProfilePreferencesRequest(timezone_iana="Invalid/Timezone")
