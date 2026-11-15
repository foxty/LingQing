"""Sensitive fields for data source ``config`` (GET redact, merge keys align with ``password`` leaves)."""

from __future__ import annotations

from apps.shared.external_systems.data_source.catalog_sync import METADATA_SYNC_CONFIG_KEY
from apps.shared.utils.sensitive_redaction import SecretLeafSpec

DATA_SOURCE_CONFIG_ROOT = "config"

DATA_SOURCE_GET_SECRET_SPECS: tuple[SecretLeafSpec, ...] = (
    SecretLeafSpec(f"{DATA_SOURCE_CONFIG_ROOT}.password", ("password",)),
    SecretLeafSpec(
        f"{DATA_SOURCE_CONFIG_ROOT}.{METADATA_SYNC_CONFIG_KEY}.password",
        (METADATA_SYNC_CONFIG_KEY, "password"),
    ),
)

# PATCH merge / preserve: only ``password`` leaves on data-source config today.
DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS: frozenset[str] = frozenset({"password"})

# User-mode query/test: drop shared login from stored template before overlaying BYOT secrets.
DATA_SOURCE_USER_MODE_STRIP_KEYS: frozenset[str] = frozenset(
    DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS | {"username", "user", "connection_url"}
)