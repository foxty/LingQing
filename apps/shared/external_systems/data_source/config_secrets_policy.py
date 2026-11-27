"""Secret policy for data-source ``config`` JSON (single source of truth)."""

from __future__ import annotations

from typing import Any

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.secret_policy import JsonSecretPolicy, TemplateStripPolicy
from apps.shared.utils.sensitive_redaction import SecretLeafSpec

# Keep in sync with ``catalog_sync.METADATA_SYNC_CONFIG_KEY`` / ``user_oauth.USER_OAUTH_CONFIG_KEY``
# (literal here to avoid import cycles with ``credentials``).
METADATA_SYNC_CONFIG_KEY = "metadata_sync"
USER_OAUTH_CONFIG_KEY = "user_oauth"

DATA_SOURCE_CONFIG_ROOT = "config"

MERGE_PRESERVE_LEAVES: frozenset[str] = frozenset({"password", "client_secret"})

IDENTITY_TEMPLATE_STRIP_KEYS: frozenset[str] = frozenset({"username", "user", "connection_url"})

_DATA_SOURCE_TEMPLATE_STRIP = TemplateStripPolicy(
    top_level_keys=MERGE_PRESERVE_LEAVES | IDENTITY_TEMPLATE_STRIP_KEYS,
    retain_subtrees=((USER_OAUTH_CONFIG_KEY,),),
)

DATA_SOURCE_CONFIG_POLICY = JsonSecretPolicy(
    root=DATA_SOURCE_CONFIG_ROOT,
    encrypt_leaves=INTEGRATION_SECRET_LEAF_KEYS,
    get_specs=(
        SecretLeafSpec(f"{DATA_SOURCE_CONFIG_ROOT}.password", ("password",)),
        SecretLeafSpec(
            f"{DATA_SOURCE_CONFIG_ROOT}.{METADATA_SYNC_CONFIG_KEY}.password",
            (METADATA_SYNC_CONFIG_KEY, "password"),
        ),
        SecretLeafSpec(
            f"{DATA_SOURCE_CONFIG_ROOT}.{USER_OAUTH_CONFIG_KEY}.client_secret",
            (USER_OAUTH_CONFIG_KEY, "client_secret"),
        ),
    ),
    merge_preserve_leaves=MERGE_PRESERVE_LEAVES,
    template_strip=_DATA_SOURCE_TEMPLATE_STRIP,
)


def prepare_data_source_config_for_storage(
    config: dict[str, Any],
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    """Encrypt all integration-shaped secret leaves in persisted data-source config."""
    from apps.shared.utils.secret_engines import encrypt_config

    cipher = cipher or FieldCipher()
    return encrypt_config(config, DATA_SOURCE_CONFIG_POLICY, cipher=cipher)


def decrypt_data_source_config_from_storage(
    config: dict[str, Any] | None,
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    """Decrypt persisted data-source config for runtime (connections, resolver, domain mapping)."""
    if not config:
        return {}
    from apps.shared.utils.secret_engines import decrypt_config

    cipher = cipher or FieldCipher()
    return decrypt_config(config, DATA_SOURCE_CONFIG_POLICY, cipher=cipher)