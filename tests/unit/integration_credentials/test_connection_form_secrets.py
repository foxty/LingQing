"""User integration GET secret shaping for connection forms."""

from apps.shared.external_systems.credentials.adapters import redact_user_integration_secrets_for_api
from apps.shared.utils.secret_wire import is_display_mask


def test_redact_splits_public_vs_masked_paths():
    secrets, masked = redact_user_integration_secrets_for_api(
        {"username": "alice", "password": "secret-value-long", "host": "localhost"}
    )
    assert secrets["username"] == "alice"
    assert secrets["host"] == "localhost"
    assert is_display_mask(secrets["password"])
    assert masked == ["secrets.password"]


def test_redact_ignores_empty_values():
    secrets, masked = redact_user_integration_secrets_for_api({"username": " ", "password": "long-enough-secret"})
    assert "username" not in secrets
    assert "password" in secrets
    assert masked == ["secrets.password"]