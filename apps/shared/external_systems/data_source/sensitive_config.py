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


def datasource_audit_credential_field_names(config: dict | None) -> list[str]:
    """Leaf paths with stored secrets — aligned with ``DATA_SOURCE_GET_SECRET_SPECS``."""
    if not config:
        return []

    from apps.shared.utils.sensitive_redaction import (
        collect_stored_secret_paths,
        config_has_secret_value,
        get_config_leaf,
    )

    names: list[str] = []
    for spec in DATA_SOURCE_GET_SECRET_SPECS:
        if config_has_secret_value(get_config_leaf(config, spec.leaf_path)):
            leaf_name = ".".join(spec.leaf_path)
            if leaf_name not in names:
                names.append(leaf_name)

    for path in collect_stored_secret_paths(
        config,
        root_prefix="",
        sensitive_leaf_keys=DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS,
    ):
        if path not in names:
            names.append(path)

    return sorted(names)