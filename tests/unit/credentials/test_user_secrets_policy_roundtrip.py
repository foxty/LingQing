"""Round-trip encrypt for BYOT user binding secrets."""

from __future__ import annotations

from apps.shared.external_systems.credentials.user_secrets_policy import (
    USER_BINDING_POLICY,
    prepare_user_binding_secrets_for_storage,
)
from apps.shared.utils.field_cipher import FieldCipher

_CIPHER_KEY = "synthetic-user-binding-roundtrip-key"


def test_prepare_user_binding_encrypts_integration_leaves():
    cipher = FieldCipher(_CIPHER_KEY)
    plain = {"username": "alice", "password": "user-db-password", "api_key": "k"}
    stored = prepare_user_binding_secrets_for_storage(plain, cipher=cipher)
    assert stored["username"] == "alice"
    assert stored["password"].startswith("enc:")
    assert stored["api_key"].startswith("enc:")

    restored = cipher.decrypt_dict(stored, sensitive_fields=USER_BINDING_POLICY.encrypt_leaves)
    assert restored == plain
