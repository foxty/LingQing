"""BYOT sensitive_config: GET paths and user-mode strip key invariants."""

from apps.shared.external_systems.credentials.sensitive_config import (
    API_CONNECTOR_USER_MODE_STRIP_KEYS,
    DATA_SOURCE_USER_MODE_STRIP_KEYS,
    USER_INTEGRATION_SECRETS_ROOT,
    USER_INTEGRATION_GET_SECRET_SPECS,
)
from apps.shared.external_systems.data_source.sensitive_config import (
    DATA_SOURCE_USER_MODE_STRIP_KEYS as DATA_SOURCE_MODULE_STRIP_KEYS,
)
from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS


def test_user_integration_get_specs_use_secrets_root():
    assert USER_INTEGRATION_GET_SECRET_SPECS
    assert all(spec.response_path.startswith(f"{USER_INTEGRATION_SECRETS_ROOT}.") for spec in USER_INTEGRATION_GET_SECRET_SPECS)


def test_data_source_user_mode_strip_keys_match_data_source_module_copy():
    assert DATA_SOURCE_USER_MODE_STRIP_KEYS == DATA_SOURCE_MODULE_STRIP_KEYS


def test_api_connector_user_mode_strip_keys_are_integration_leaves():
    assert API_CONNECTOR_USER_MODE_STRIP_KEYS == INTEGRATION_SECRET_LEAF_KEYS
