"""BYOT connection GET redaction (approach A)."""

from apps.shared.external_systems.credentials.adapters import redact_user_integration_secrets_for_api
from apps.shared.utils.secret_wire import is_display_mask


def test_redact_masks_password_and_lists_masked_fields():
    secrets, masked = redact_user_integration_secrets_for_api(
        {"username": "alice", "password": "user-secret-value"}
    )
    assert masked == ["secrets.password"]
    assert secrets["username"] == "alice"
    assert is_display_mask(secrets["password"])
    assert "user-secret" not in secrets["password"]
