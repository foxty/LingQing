"""Secret policy for BYOT ``secrets_enc`` user binding blobs."""

from __future__ import annotations

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.secret_policy import JsonSecretPolicy
from apps.shared.utils.sensitive_redaction import SecretLeafSpec

USER_INTEGRATION_SECRETS_ROOT = "secrets"

USER_BINDING_POLICY = JsonSecretPolicy(
    root=USER_INTEGRATION_SECRETS_ROOT,
    encrypt_leaves=INTEGRATION_SECRET_LEAF_KEYS,
    get_specs=tuple(
        SecretLeafSpec(f"{USER_INTEGRATION_SECRETS_ROOT}.{key}", (key,))
        for key in sorted(INTEGRATION_SECRET_LEAF_KEYS)
    ),
    merge_preserve_leaves=INTEGRATION_SECRET_LEAF_KEYS,
    template_strip=None,
)


def prepare_user_binding_secrets_for_storage(
    secrets: dict,
    *,
    cipher=None,
) -> dict:
    from apps.shared.utils.field_cipher import FieldCipher
    from apps.shared.utils.secret_engines import encrypt_config

    cipher = cipher or FieldCipher()
    return encrypt_config(secrets, USER_BINDING_POLICY, cipher=cipher)
