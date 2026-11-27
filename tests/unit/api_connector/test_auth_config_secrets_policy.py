"""API connector auth_config secret policy invariants."""

from apps.shared.external_systems.api_connector.auth_config_secrets_policy import AUTH_CONFIG_POLICY
from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS


def test_auth_config_encrypt_leaves_use_integration_keys():
    assert AUTH_CONFIG_POLICY.encrypt_leaves == INTEGRATION_SECRET_LEAF_KEYS


def test_integration_leaves_match_auth_config_user_mode_strip():
    assert INTEGRATION_SECRET_LEAF_KEYS == AUTH_CONFIG_POLICY.user_mode_strip_top_level