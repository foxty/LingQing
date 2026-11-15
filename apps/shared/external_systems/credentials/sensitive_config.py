"""BYOT credential GET paths and helpers (keys: ``integration_secret_keys``)."""

from __future__ import annotations

from collections.abc import Sequence

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS

USER_INTEGRATION_SECRETS_ROOT = "secrets"

# Plaintext user secret blob uses the same leaf names as connector auth.
USER_INTEGRATION_SENSITIVE_LEAF_KEYS: frozenset[str] = INTEGRATION_SECRET_LEAF_KEYS

# Top-level keys stripped from shared templates before overlaying BYOT secrets (no cross-package imports).
DATA_SOURCE_USER_MODE_STRIP_KEYS: frozenset[str] = frozenset(
    {"password", "username", "user", "connection_url"}
)
API_CONNECTOR_USER_MODE_STRIP_KEYS: frozenset[str] = INTEGRATION_SECRET_LEAF_KEYS


def masked_fields_for_configured_secret_keys(secret_keys: Sequence[str]) -> list[str]:
    return [f"{USER_INTEGRATION_SECRETS_ROOT}.{key}" for key in sorted(secret_keys)]
