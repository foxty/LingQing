"""BYOT user-binding policy invariants."""

from apps.shared.external_systems.credentials.user_secrets_policy import (
    USER_BINDING_POLICY,
    USER_INTEGRATION_SECRETS_ROOT,
)
from apps.shared.external_systems.data_source.config_secrets_policy import DATA_SOURCE_CONFIG_POLICY
from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS


def test_user_binding_get_specs_use_secrets_root():
    assert all(
        spec.response_path.startswith(f"{USER_INTEGRATION_SECRETS_ROOT}.")
        for spec in USER_BINDING_POLICY.get_specs
    )


def test_integration_leaves_shared_with_data_source_encrypt():
    assert INTEGRATION_SECRET_LEAF_KEYS == DATA_SOURCE_CONFIG_POLICY.encrypt_leaves
    assert USER_BINDING_POLICY.encrypt_leaves == INTEGRATION_SECRET_LEAF_KEYS
