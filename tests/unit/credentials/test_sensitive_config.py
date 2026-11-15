"""BYOT sensitive_config: GET paths and user-mode strip key invariants."""

from apps.shared.external_systems.credentials.sensitive_config import (
    API_CONNECTOR_USER_MODE_STRIP_KEYS,
    DATA_SOURCE_USER_MODE_STRIP_KEYS,
    USER_INTEGRATION_SECRETS_ROOT,
    masked_fields_for_configured_secret_keys,
)
from apps.shared.external_systems.data_source.sensitive_config import (
    DATA_SOURCE_USER_MODE_STRIP_KEYS as DATA_SOURCE_MODULE_STRIP_KEYS,
)
from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS


def test_masked_fields_for_configured_secret_keys_sorted_under_secrets_root():
    assert masked_fields_for_configured_secret_keys(["password", "api_key"]) == [
        f"{USER_INTEGRATION_SECRETS_ROOT}.api_key",
        f"{USER_INTEGRATION_SECRETS_ROOT}.password",
    ]


def test_data_source_user_mode_strip_keys_match_data_source_module_copy():
    """Credentials avoids importing data_source at runtime — tests keep frozensets aligned."""
    assert DATA_SOURCE_USER_MODE_STRIP_KEYS == DATA_SOURCE_MODULE_STRIP_KEYS


def test_api_connector_user_mode_strip_keys_are_integration_leaves():
    assert API_CONNECTOR_USER_MODE_STRIP_KEYS == INTEGRATION_SECRET_LEAF_KEYS
