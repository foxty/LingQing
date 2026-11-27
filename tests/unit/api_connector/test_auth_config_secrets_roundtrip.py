"""Round-trip encrypt, decrypt, and GET redact for connector auth_config policy."""

from __future__ import annotations

from apps.shared.external_systems.api_connector.auth_config_secrets_policy import (
    AUTH_CONFIG_ROOT,
    decrypt_auth_config_from_storage,
    prepare_auth_config_for_storage,
    redact_auth_config_for_api,
)
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.secret_wire import is_display_mask

_CIPHER_KEY = "synthetic-connector-auth-roundtrip-key"


def test_prepare_decrypt_restores_nested_integration_secrets():
    cipher = FieldCipher(_CIPHER_KEY)
    plain = {
        "client_id": "app",
        "endpoint": "https://api.example.test/v1",
        "api_key": "sk-integration-secret",
        "extra_config": {"app_secret": "nested-secret-value", "tenant": "t1"},
    }
    stored = prepare_auth_config_for_storage(plain, cipher=cipher)
    assert stored["api_key"].startswith("enc:")
    assert stored["extra_config"]["app_secret"].startswith("enc:")

    restored = decrypt_auth_config_from_storage(stored, cipher=cipher)
    assert restored == plain


def test_redact_auth_config_for_api_masks_and_lists_nested_paths():
    auth = {
        "client_id": "app",
        "api_key": "sk-long-enough-secret",
        "extra_config": {"app_secret": "nested-long-secret"},
    }
    masked, paths = redact_auth_config_for_api(auth)
    assert is_display_mask(masked["api_key"])
    assert is_display_mask(masked["extra_config"]["app_secret"])
    assert f"{AUTH_CONFIG_ROOT}.api_key" in paths
    assert f"{AUTH_CONFIG_ROOT}.extra_config.app_secret" in paths