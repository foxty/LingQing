"""Unit tests for secret policy engines."""

from __future__ import annotations

from apps.shared.external_systems.data_source.config_secrets_policy import DATA_SOURCE_CONFIG_POLICY
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.external_systems.credentials.user_secrets_policy import USER_BINDING_POLICY
from apps.shared.utils.secret_engines import (
    decrypt_config,
    encrypt_config,
    merge_config,
    redact_for_get,
    strip_template,
)
from apps.shared.utils.secret_wire import is_display_mask
from apps.shared.utils.secret_policy import TemplateStripPolicy


def test_strip_template_respects_retain_subtrees():
    template = TemplateStripPolicy(
        top_level_keys=frozenset({"password", "client_secret", "username"}),
        retain_subtrees=(("user_oauth",),),
    )
    raw = {
        "host": "adb.example.net",
        "password": "shared-pat",
        "client_secret": "top-level",
        "username": "u",
        "user_oauth": {"client_secret": "admin-secret", "client_id": "c"},
    }
    stripped = strip_template(raw, template)
    assert stripped["host"] == "adb.example.net"
    assert "password" not in stripped
    assert "username" not in stripped
    assert stripped["user_oauth"]["client_secret"] == "admin-secret"


def test_data_source_policy_strip_matches_legacy_user_mode_template():
    raw = {
        "readOnly": True,
        "host": "localhost",
        "database": "db",
        "username": "u",
        "password": "p",
        "connection_url": "postgresql://u:p@localhost/db",
    }
    template = DATA_SOURCE_CONFIG_POLICY.template_strip
    assert template is not None
    stripped = strip_template(raw, template)
    assert stripped == {"readOnly": True, "host": "localhost", "database": "db"}


def test_encrypt_config_uses_policy_leaves_recursively():
    cipher = FieldCipher("synthetic-secret-engine-key")
    policy = DATA_SOURCE_CONFIG_POLICY
    data = {
        "password": "root",
        "user_oauth": {"client_secret": "nested"},
    }
    encrypted = encrypt_config(data, policy, cipher=cipher)
    assert encrypted["password"].startswith("enc:")
    assert encrypted["user_oauth"]["client_secret"].startswith("enc:")
    decrypted = cipher.decrypt_dict(encrypted, sensitive_fields=set(policy.encrypt_leaves))
    assert decrypted == data


def test_decrypt_config_reverses_encrypt_config():
    cipher = FieldCipher("synthetic-secret-engine-decrypt-key")
    data = {"password": "root", "host": "h"}
    encrypted = encrypt_config(data, DATA_SOURCE_CONFIG_POLICY, cipher=cipher)
    assert decrypt_config(encrypted, DATA_SOURCE_CONFIG_POLICY, cipher=cipher) == data


def test_redact_for_get_uses_policy_get_specs():
    payload = {"username": "u", "password": "long-user-password"}
    redacted, paths = redact_for_get(
        payload,
        USER_BINDING_POLICY,
        mask_value=lambda raw: "****" if isinstance(raw, str) and raw.strip() else None,
    )
    assert is_display_mask(redacted["password"])
    assert paths == ["secrets.password"]
    assert redacted["username"] == "u"


def test_merge_config_preserves_secret_when_omitted():
    existing = {"client_id": "c", "client_secret": "enc:stored"}
    incoming = {"client_id": "c-next"}
    merged = merge_config(existing, incoming, DATA_SOURCE_CONFIG_POLICY)
    assert merged["client_secret"] == "enc:stored"
    assert merged["client_id"] == "c-next"