"""Unit tests for FieldCipher with configurable sensitive fields."""

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.utils.field_cipher import SENSITIVE_FIELD_KEYS, FieldCipher


class TestFieldCipherEncryptDecrypt:
    """Test encryption/decryption with explicit sensitive_fields parameter."""

    def test_encrypt_dict_with_explicit_fields(self):
        """encrypt_dict should only encrypt fields in sensitive_fields."""
        cipher = FieldCipher()
        data = {"api_key": "secret123", "name": "test"}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted["api_key"].startswith("enc:")
        assert encrypted["name"] == "test"

    def test_decrypt_dict_with_explicit_fields(self):
        """decrypt_dict should only decrypt fields in sensitive_fields."""
        cipher = FieldCipher()
        data = {"api_key": "secret123"}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields={"api_key"})
        assert decrypted["api_key"] == "secret123"

    def test_decrypt_dict_auto_detect_encrypted_values(self):
        """decrypt_dict without sensitive_fields should auto-detect 'enc:' prefix."""
        cipher = FieldCipher()
        data = {"api_key": "secret123", "name": "not-encrypted", "nested": {"token": "nested-secret"}}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key", "token"})

        # Verify encryption happened
        assert encrypted["api_key"].startswith("enc:")
        assert encrypted["name"] == "not-encrypted"
        assert encrypted["nested"]["token"].startswith("enc:")

        # Auto-decrypt without specifying fields
        decrypted = cipher.decrypt_dict(encrypted)
        assert decrypted == data

    def test_mask_dict_with_explicit_fields(self):
        """mask_dict should only mask fields in sensitive_fields."""
        data = {"api_key": "sk-1234567890", "name": "test"}
        # "sk-1234567890" has 13 chars: first 2 + 9 asterisks + last 2 = "sk*********90"
        masked = FieldCipher.mask_dict(data, sensitive_fields={"api_key"})
        assert masked["api_key"] == "sk*********90"
        assert masked["name"] == "test"

    def test_all_default_sensitive_fields_can_be_encrypted(self):
        """All fields in SENSITIVE_FIELD_KEYS should be encryptable when specified."""
        cipher = FieldCipher()
        data = {
            "api_key": "key1",
            "key_value": "key2",
            "token": "key3",
            "access_token": "key4",
            "refresh_token": "key5",
            "client_secret": "key6",
            "password": "key7",
            "name": "should_not_encrypt",
        }
        encrypted = cipher.encrypt_dict(data, sensitive_fields=SENSITIVE_FIELD_KEYS)

        # All sensitive fields should be encrypted
        assert encrypted["api_key"].startswith("enc:")
        assert encrypted["key_value"].startswith("enc:")
        assert encrypted["token"].startswith("enc:")
        assert encrypted["access_token"].startswith("enc:")
        assert encrypted["refresh_token"].startswith("enc:")
        assert encrypted["client_secret"].startswith("enc:")
        assert encrypted["password"].startswith("enc:")

        # Non-sensitive field should not be encrypted
        assert encrypted["name"] == "should_not_encrypt"


class TestFieldCipherCustomSensitiveFields:
    """Test explicit sensitive_fields parameter."""

    def test_encrypt_dict_with_custom_fields(self):
        """encrypt_dict should only encrypt fields in sensitive_fields."""
        cipher = FieldCipher()
        data = {"custom_secret": "secret123", "api_key": "should-not-encrypt"}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"custom_secret"})
        assert encrypted["custom_secret"].startswith("enc:")
        assert encrypted["api_key"] == "should-not-encrypt"

    def test_decrypt_dict_with_custom_fields(self):
        """decrypt_dict should only decrypt fields in sensitive_fields."""
        cipher = FieldCipher()
        data = {"custom_secret": "secret123"}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"custom_secret"})
        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields={"custom_secret"})
        assert decrypted["custom_secret"] == "secret123"

    def test_mask_dict_with_custom_fields(self):
        """mask_dict should only mask fields in sensitive_fields."""
        data = {"custom_secret": "sk-1234567890", "api_key": "visible"}
        masked = FieldCipher.mask_dict(data, sensitive_fields={"custom_secret"})
        # "sk-1234567890" has 13 chars: first 2 + 9 asterisks + last 2 = "sk*********90"
        assert masked["custom_secret"] == "sk*********90"
        assert masked["api_key"] == "visible"

    def test_empty_sensitive_fields_raises_error_encrypt(self):
        """Empty sensitive_fields should raise ValidationError on encrypt."""
        cipher = FieldCipher()
        with pytest.raises(ValidationError, match="sensitive_fields cannot be empty"):
            cipher.encrypt_dict({"key": "value"}, sensitive_fields=set())

    def test_empty_sensitive_fields_raises_error_decrypt(self):
        """Empty sensitive_fields should raise ValidationError on decrypt."""
        cipher = FieldCipher()
        with pytest.raises(ValidationError, match="sensitive_fields cannot be empty"):
            cipher.decrypt_dict({"key": "value"}, sensitive_fields=set())

    def test_empty_sensitive_fields_raises_error_mask(self):
        """Empty sensitive_fields should raise ValidationError on mask."""
        with pytest.raises(ValidationError, match="sensitive_fields cannot be empty"):
            FieldCipher.mask_dict({"key": "value"}, sensitive_fields=set())

    def test_missing_sensitive_fields_raises_error(self):
        """Missing sensitive_fields parameter should raise TypeError for encrypt and mask."""
        cipher = FieldCipher()
        with pytest.raises(TypeError):
            cipher.encrypt_dict({"key": "value"})
        with pytest.raises(TypeError):
            FieldCipher.mask_dict({"key": "value"})

        # But decrypt_dict should work without sensitive_fields (auto-detect)
        cipher2 = FieldCipher()
        data = {"api_key": "secret123"}
        encrypted = cipher2.encrypt_dict(data, sensitive_fields={"api_key"})
        decrypted = cipher2.decrypt_dict(encrypted)  # Should not raise
        assert decrypted["api_key"] == "secret123"

    def test_custom_fields_override_defaults(self):
        """Custom fields should be used instead of any defaults."""
        cipher = FieldCipher()
        data = {"api_key": "secret", "custom_field": "secret2"}

        # Only encrypt custom_field, not api_key
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"custom_field"})
        assert encrypted["api_key"] == "secret"  # Not encrypted
        assert encrypted["custom_field"].startswith("enc:")


class TestFieldCipherNestedStructures:
    """Test encryption/decryption with nested dicts and lists."""

    def test_auto_decrypt_nested_structures(self):
        """Auto-detect should decrypt nested encrypted values."""
        cipher = FieldCipher()
        data = {
            "auth": {"api_key": "key1", "token": "token1"},
            "endpoints": [
                {"url": "https://api1.com", "api_key": "key2"},
                {"url": "https://api2.com", "api_key": "key3"},
            ],
            "name": "not-encrypted",
        }
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key", "token"})

        # Auto-decrypt without sensitive_fields
        decrypted = cipher.decrypt_dict(encrypted)
        assert decrypted == data

    def test_auto_decrypt_mixed_encrypted_and_plain(self):
        """Auto-detect should only decrypt values with 'enc:' prefix."""
        cipher = FieldCipher()
        data = {
            "encrypted_field": "secret",
            "plain_field": "visible",
            "nested": {"encrypted": "hidden", "plain": "also-visible"},
        }
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"encrypted_field", "encrypted"})

        # Add some non-encrypted fields manually
        encrypted["already_plain"] = "was-never-encrypted"

        # Auto-decrypt
        decrypted = cipher.decrypt_dict(encrypted)
        assert decrypted["encrypted_field"] == "secret"
        assert decrypted["plain_field"] == "visible"
        assert decrypted["nested"]["encrypted"] == "hidden"
        assert decrypted["nested"]["plain"] == "also-visible"
        assert decrypted["already_plain"] == "was-never-encrypted"

    def test_encrypt_nested_dict_with_custom_fields(self):
        """Should encrypt sensitive fields in nested dicts."""
        cipher = FieldCipher()
        data = {"auth": {"api_key": "secret123"}, "config": {"name": "test"}}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted["auth"]["api_key"].startswith("enc:")
        assert encrypted["config"]["name"] == "test"

    def test_decrypt_nested_dict_with_custom_fields(self):
        """Should decrypt sensitive fields in nested dicts."""
        cipher = FieldCipher()
        data = {"auth": {"api_key": "secret123"}, "config": {"name": "test"}}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields={"api_key"})
        assert decrypted == data

    def test_encrypt_list_of_dicts_with_custom_fields(self):
        """Should encrypt sensitive fields in lists of dicts."""
        cipher = FieldCipher()
        data = [{"api_key": "secret1"}, {"api_key": "secret2"}]
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted[0]["api_key"].startswith("enc:")
        assert encrypted[1]["api_key"].startswith("enc:")

    def test_decrypt_list_of_dicts_with_custom_fields(self):
        """Should decrypt sensitive fields in lists of dicts."""
        cipher = FieldCipher()
        data = [{"api_key": "secret1"}, {"api_key": "secret2"}]
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields={"api_key"})
        assert decrypted == data

    def test_deeply_nested_structure(self):
        """Should handle deeply nested structures correctly."""
        cipher = FieldCipher()
        data = {"level1": {"level2": {"level3": {"api_key": "deep_secret"}}}}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted["level1"]["level2"]["level3"]["api_key"].startswith("enc:")

        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields={"api_key"})
        assert decrypted == data


class TestFieldCipherAPIConnectorIntegration:
    """Test with realistic API connector auth_config."""

    def test_encrypt_api_connector_auth_config(self):
        """Should encrypt API connector auth fields."""
        cipher = FieldCipher()
        auth_config = {
            "api_key": "sk-test-123",
            "key_name": "X-API-Key",  # Should NOT be encrypted
            "auth_type": "api_key",  # Should NOT be encrypted
        }
        sensitive_fields = {"api_key", "token", "client_secret"}

        encrypted = cipher.encrypt_dict(auth_config, sensitive_fields=sensitive_fields)
        assert encrypted["api_key"].startswith("enc:")
        assert encrypted["key_name"] == "X-API-Key"
        assert encrypted["auth_type"] == "api_key"

        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields=sensitive_fields)
        assert decrypted == auth_config

    def test_mask_api_connector_auth_config(self):
        """Should mask only sensitive fields in auth config."""
        auth_config = {"api_key": "sk-1234567890abcdef", "key_name": "X-API-Key", "auth_type": "api_key"}
        sensitive_fields = {"api_key"}

        masked = FieldCipher.mask_dict(auth_config, sensitive_fields=sensitive_fields)
        # "sk-1234567890abcdef" has 18 chars: first 2 + 14 asterisks + last 2 = "sk***************ef"
        assert masked["api_key"] == "sk***************ef"
        assert masked["key_name"] == "X-API-Key"
        assert masked["auth_type"] == "api_key"

    def test_oauth_auth_config(self):
        """Should handle OAuth auth config with multiple sensitive fields."""
        cipher = FieldCipher()
        auth_config = {
            "client_id": "public-client-id",
            "client_secret": "secret-value",
            "access_token": "token-value",
            "refresh_token": "refresh-value",
            "token_url": "https://example.com/token",
        }
        sensitive_fields = {"client_secret", "access_token", "refresh_token"}

        encrypted = cipher.encrypt_dict(auth_config, sensitive_fields=sensitive_fields)
        assert encrypted["client_id"] == "public-client-id"
        assert encrypted["client_secret"].startswith("enc:")
        assert encrypted["access_token"].startswith("enc:")
        assert encrypted["refresh_token"].startswith("enc:")
        assert encrypted["token_url"] == "https://example.com/token"

        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields=sensitive_fields)
        assert decrypted == auth_config


class TestFieldCipherEdgeCases:
    """Test edge cases and error handling."""

    def test_non_string_values_not_encrypted(self):
        """Non-string values should not be encrypted even if field name matches."""
        cipher = FieldCipher()
        data = {"api_key": 12345, "token": None, "password": True}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key", "token", "password"})
        assert encrypted["api_key"] == 12345
        assert encrypted["token"] is None
        assert encrypted["password"] is True

    def test_already_encrypted_values_not_double_encrypted(self):
        """Values starting with 'enc:' should not be double-encrypted."""
        cipher = FieldCipher()
        data = {"api_key": "enc:already_encrypted"}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted["api_key"] == "enc:already_encrypted"

    def test_env_prefix_values_not_encrypted(self):
        """Values starting with 'env:' should not be encrypted."""
        cipher = FieldCipher()
        data = {"api_key": "env:MY_API_KEY"}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted["api_key"] == "env:MY_API_KEY"

    def test_empty_dict(self):
        """Should handle empty dict gracefully."""
        cipher = FieldCipher()
        encrypted = cipher.encrypt_dict({}, sensitive_fields={"api_key"})
        assert encrypted == {}

    def test_dict_with_no_sensitive_fields(self):
        """Should return unchanged dict when no sensitive fields present."""
        cipher = FieldCipher()
        data = {"name": "test", "value": 123}
        encrypted = cipher.encrypt_dict(data, sensitive_fields={"api_key"})
        assert encrypted == data

    def test_mask_short_values(self):
        """Should mask short values (<=4 chars) with all asterisks."""
        data = {"api_key": "abc", "token": "abcd", "secret": "abcde"}
        masked = FieldCipher.mask_dict(data, sensitive_fields={"api_key", "token", "secret"})
        assert masked["api_key"] == "***"
        assert masked["token"] == "****"
        assert masked["secret"] == "ab*de"

    def test_round_trip_with_complex_structure(self):
        """Should preserve data through encrypt-decrypt round trip."""
        cipher = FieldCipher()
        data = {
            "auth": {"api_key": "secret123", "type": "bearer"},
            "endpoints": [
                {"url": "https://api1.com", "token": "token1"},
                {"url": "https://api2.com", "token": "token2"},
            ],
            "metadata": {"name": "test", "password": "pass123"},
        }
        sensitive_fields = {"api_key", "token", "password"}

        encrypted = cipher.encrypt_dict(data, sensitive_fields=sensitive_fields)
        decrypted = cipher.decrypt_dict(encrypted, sensitive_fields=sensitive_fields)
        assert decrypted == data
