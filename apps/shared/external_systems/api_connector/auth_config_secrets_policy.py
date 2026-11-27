"""Secret policy for API connector ``auth_config`` JSON."""

from __future__ import annotations

from typing import Any

from apps.shared.external_systems.byot_template_strip import CONNECTOR_AUTH_TEMPLATE_STRIP
from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.secret_policy import JsonSecretPolicy
from apps.shared.utils.sensitive_redaction import SecretLeafSpec, collect_stored_secret_paths

AUTH_CONFIG_ROOT = "auth_config"

AUTH_CONFIG_POLICY = JsonSecretPolicy(
    root=AUTH_CONFIG_ROOT,
    encrypt_leaves=INTEGRATION_SECRET_LEAF_KEYS,
    get_specs=tuple(
        SecretLeafSpec(f"{AUTH_CONFIG_ROOT}.{key}", (key,)) for key in sorted(INTEGRATION_SECRET_LEAF_KEYS)
    ),
    merge_preserve_leaves=INTEGRATION_SECRET_LEAF_KEYS,
    template_strip=CONNECTOR_AUTH_TEMPLATE_STRIP,
)


def prepare_auth_config_for_storage(
    auth_config: dict[str, Any],
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    """Encrypt integration secret leaves on connector ``auth_config``."""
    from apps.shared.utils.secret_engines import encrypt_config

    cipher = cipher or FieldCipher()
    return encrypt_config(auth_config, AUTH_CONFIG_POLICY, cipher=cipher)


def decrypt_auth_config_from_storage(
    auth_config: dict[str, Any],
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    from apps.shared.utils.secret_engines import decrypt_config

    cipher = cipher or FieldCipher()
    return decrypt_config(auth_config, AUTH_CONFIG_POLICY, cipher=cipher)


def redact_auth_config_for_api(auth_config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Mask connector auth for GET; ``masked_fields`` includes nested integration leaves."""
    masked_fields = collect_stored_secret_paths(
        auth_config,
        root_prefix=AUTH_CONFIG_ROOT,
        sensitive_leaf_keys=AUTH_CONFIG_POLICY.encrypt_leaves,
    )
    masked_auth = FieldCipher.mask_dict(
        auth_config,
        sensitive_fields=set(AUTH_CONFIG_POLICY.encrypt_leaves),
    )
    return masked_auth, masked_fields