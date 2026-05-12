"""Helpers for encrypting/decrypting sensitive connector fields."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from apps.config import EnvConfig
from apps.shared.core.exceptions import ValidationError

SENSITIVE_FIELD_KEYS = {
    "api_key",
    "key_value",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "password",
    "app_secret",  # For custom auth (e.g., Kingdee ERP)
}

# Aliases for backward compatibility and domain-specific naming
AUTH_CONFIG_SENSITIVE_FIELDS = SENSITIVE_FIELD_KEYS


class FieldCipher:
    """Encrypt/decrypt fields with Fernet.

    Uses FIELD_ENCRYPTION_KEY when present; otherwise derives a stable key from
    SECRET_KEY to keep local/dev environments simple.
    """

    def __init__(self, key: str | None = None):
        material = key or getattr(EnvConfig, "FIELD_ENCRYPTION_KEY", "") or EnvConfig.SECRET_KEY
        if not material:
            raise ValidationError("Missing encryption key material")
        digest = hashlib.sha256(material.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        if value.startswith("enc:") or value.startswith("env:"):
            return value
        token = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    def decrypt(self, value: str) -> str:
        if value.startswith("env:"):
            return value
        if not value.startswith("enc:"):
            return value
        token = value[4:]
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValidationError("Invalid encrypted field") from exc

    def encrypt_dict(
        self,
        data: dict[str, Any],
        sensitive_fields: set[str],
    ) -> dict[str, Any]:
        """Encrypt sensitive fields in a dict.

        Args:
            data: Dict potentially containing sensitive fields
            sensitive_fields: Set of field names to encrypt (required).

        Returns:
            Dict with sensitive fields encrypted (prefixed with 'enc:')

        Raises:
            ValidationError: If sensitive_fields is empty
        """
        if not sensitive_fields:
            raise ValidationError("sensitive_fields cannot be empty")
        return self._walk(data, encrypt=True, sensitive_fields=sensitive_fields)

    def decrypt_dict(
        self,
        data: dict[str, Any],
        sensitive_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """Decrypt sensitive fields in a dict.

        Args:
            data: Dict with encrypted sensitive fields
            sensitive_fields: Set of field names to decrypt (optional).
                             If None, auto-detects encrypted values by 'enc:' prefix.

        Returns:
            Dict with sensitive fields decrypted
        """
        if sensitive_fields is not None and not sensitive_fields:
            raise ValidationError("sensitive_fields cannot be empty")

        # If no sensitive_fields specified, auto-detect encrypted values
        if sensitive_fields is None:
            return self._walk_auto_decrypt(data)

        return self._walk(data, encrypt=False, sensitive_fields=sensitive_fields)

    def _walk(
        self,
        value: Any,
        *,
        encrypt: bool,
        sensitive_fields: set[str],
    ) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(v, str) and k in sensitive_fields:
                    out[k] = self.encrypt(v) if encrypt else self.decrypt(v)
                else:
                    out[k] = self._walk(v, encrypt=encrypt, sensitive_fields=sensitive_fields)
            return out
        if isinstance(value, list):
            return [self._walk(item, encrypt=encrypt, sensitive_fields=sensitive_fields) for item in value]
        return value

    def _walk_auto_decrypt(self, value: Any) -> Any:
        """Recursively decrypt all values that start with 'enc:' prefix.

        Used when sensitive_fields is not specified for decrypt_dict.
        """
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                out[k] = self._walk_auto_decrypt(v)
            return out
        if isinstance(value, list):
            return [self._walk_auto_decrypt(item) for item in value]
        if isinstance(value, str) and value.startswith("enc:"):
            return self.decrypt(value)
        return value

    @staticmethod
    def mask_value(value: str) -> str:
        """Mask a single sensitive value for logging/display.

        Args:
            value: The sensitive string value to mask

        Returns:
            Masked string (e.g., 'sk****key' for long values, '****' for short values)
        """
        if not value:
            return ""
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]

    @staticmethod
    def is_masked(value: str) -> bool:
        """Check if a value is already masked (contains asterisks in the middle).

        Args:
            value: String value to check

        Returns:
            True if the value appears to be masked (e.g., 'sk****key', '****')
        """
        if not value or len(value) < 4:
            return False
        # Masked values have asterisks in the middle (not at start or end)
        # Pattern: starts with non-*, has * in middle, may end with non-*
        return "*" in value[1:-1] and not value.startswith("*")

    @staticmethod
    def mask_dict(
        data: dict[str, Any],
        sensitive_fields: set[str],
    ) -> dict[str, Any]:
        """Mask sensitive fields for logging/display.

        Args:
            data: Dict potentially containing sensitive fields
            sensitive_fields: Set of field names to mask (required).

        Returns:
            Dict with sensitive fields masked (e.g., 'sk****key')

        Raises:
            ValidationError: If sensitive_fields is empty
        """
        if not sensitive_fields:
            raise ValidationError("sensitive_fields cannot be empty")

        def _mask(v: Any, key: str | None = None) -> Any:
            if isinstance(v, dict):
                return {k: _mask(sub_v, k) for k, sub_v in v.items()}
            if isinstance(v, list):
                return [_mask(item, key) for item in v]
            if isinstance(v, str) and key in sensitive_fields:
                return FieldCipher.mask_value(v)
            return v

        return _mask(data)

    @staticmethod
    def dumps(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def loads(data: str) -> dict[str, Any]:
        raw = json.loads(data)
        if not isinstance(raw, dict):
            raise ValidationError("auth_config must be a JSON object")
        return raw
