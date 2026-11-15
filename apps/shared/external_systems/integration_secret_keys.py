"""Leaf key names treated as secrets in integration JSON (auth_config, BYOT blobs, nested extra_config).

``FieldCipher`` only encrypts/decrypts — callers pass ``sensitive_fields`` from the relevant
``*/sensitive_config.py`` (or this set when the payload uses standard integration key names).
"""

from __future__ import annotations

INTEGRATION_SECRET_LEAF_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "key_value",
        "token",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
        "app_secret",
    }
)