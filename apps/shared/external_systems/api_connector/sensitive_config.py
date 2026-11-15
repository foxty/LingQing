"""Sensitive fields for API connector ``auth_config`` (encrypt, mask, GET ``masked_fields``)."""

from __future__ import annotations

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS

AUTH_CONFIG_MASKED_ROOT = "auth_config_masked"

AUTH_CONFIG_SENSITIVE_LEAF_KEYS: frozenset[str] = INTEGRATION_SECRET_LEAF_KEYS

# Encrypt/mask call sites (``FieldCipher.encrypt_dict(..., sensitive_fields=…)``).
AUTH_CONFIG_SENSITIVE_FIELDS = AUTH_CONFIG_SENSITIVE_LEAF_KEYS

# User-mode BYOT: remove top-level shared auth leaves before overlaying user secrets.
API_CONNECTOR_USER_MODE_STRIP_KEYS: frozenset[str] = AUTH_CONFIG_SENSITIVE_LEAF_KEYS