"""BYOT credential GET paths and helpers (keys: ``integration_secret_keys``)."""

from __future__ import annotations

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.sensitive_redaction import SecretLeafSpec

USER_INTEGRATION_SECRETS_ROOT = "secrets"

USER_INTEGRATION_GET_SECRET_SPECS: tuple[SecretLeafSpec, ...] = tuple(
    SecretLeafSpec(f"{USER_INTEGRATION_SECRETS_ROOT}.{key}", (key,))
    for key in sorted(INTEGRATION_SECRET_LEAF_KEYS)
)

# Plaintext user secret blob uses the same leaf names as connector auth.
USER_INTEGRATION_SENSITIVE_LEAF_KEYS: frozenset[str] = INTEGRATION_SECRET_LEAF_KEYS

# Top-level keys stripped from shared templates before overlaying BYOT secrets (no cross-package imports).
DATA_SOURCE_USER_MODE_STRIP_KEYS: frozenset[str] = frozenset(
    {"password", "username", "user", "connection_url"}
)
API_CONNECTOR_USER_MODE_STRIP_KEYS: frozenset[str] = INTEGRATION_SECRET_LEAF_KEYS
