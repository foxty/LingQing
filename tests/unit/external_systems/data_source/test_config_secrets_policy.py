"""Data source config secret policy invariants."""

from apps.shared.external_systems.data_source.config_secrets_policy import (
    DATA_SOURCE_CONFIG_POLICY,
    decrypt_data_source_config_from_storage,
    prepare_data_source_config_for_storage,
)
from apps.shared.utils.field_cipher import FieldCipher


def test_prepare_and_decrypt_roundtrip_managed_postgres_password():
    cipher = FieldCipher("synthetic-managed-ds-config-key")
    plain = {"host": "h", "database": "db", "username": "u", "password": "integ_p&ss%40word"}
    stored = prepare_data_source_config_for_storage(plain, cipher=cipher)
    assert stored["password"].startswith("enc:")
    assert decrypt_data_source_config_from_storage(stored, cipher=cipher) == plain


def test_user_mode_strip_includes_identity_and_merge_leaves():
    strip = DATA_SOURCE_CONFIG_POLICY.user_mode_strip_top_level
    assert "password" in strip
    assert "client_secret" in strip
    assert "username" in strip
    assert DATA_SOURCE_CONFIG_POLICY.template_strip is not None
    assert ("user_oauth",) in DATA_SOURCE_CONFIG_POLICY.template_strip.retain_subtrees