"""Sensitive redaction helpers driven by declared specs."""

from apps.shared.external_systems.api_connector.sensitive_config import AUTH_CONFIG_MASKED_ROOT
from apps.shared.external_systems.data_source.sensitive_config import DATA_SOURCE_GET_SECRET_SPECS
from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.secret_wire import mask_secret_for_display
from apps.shared.utils.sensitive_redaction import collect_stored_secret_paths, redact_secret_leaves_for_get


def test_redact_data_source_specs_match_adapters():
    config = {
        "host": "h",
        "password": "secret-root",
        "metadata_sync": {"username": "u", "password": "sync-secret"},
    }
    redacted, paths = redact_secret_leaves_for_get(
        config,
        DATA_SOURCE_GET_SECRET_SPECS,
        mask_value=lambda raw: mask_secret_for_display(str(raw)),
    )
    assert paths == ["config.metadata_sync.password", "config.password"]
    assert "*" in redacted["metadata_sync"]["password"]
    assert redacted["host"] == "h"


def test_collect_stored_secret_paths_nested_extra_config():
    auth = {
        "login_endpoint": "/login",
        "extra_config": {"app_secret": "top-secret-value-here", "tenant": "t1"},
        "api_key": "short",
    }
    paths = collect_stored_secret_paths(
        auth,
        root_prefix=AUTH_CONFIG_MASKED_ROOT,
        sensitive_leaf_keys=INTEGRATION_SECRET_LEAF_KEYS,
    )
    assert "auth_config_masked.api_key" in paths
    assert "auth_config_masked.extra_config.app_secret" in paths
    assert "auth_config_masked.login_endpoint" not in paths


def test_redact_omits_leaf_when_mask_returns_none():
    from apps.shared.external_systems.data_source.sensitive_config import (
        DATA_SOURCE_GET_SECRET_SPECS,
    )

    config = {"host": "h", "password": "enc:bad-ciphertext"}
    redacted, paths = redact_secret_leaves_for_get(
        config,
        DATA_SOURCE_GET_SECRET_SPECS,
        mask_value=lambda _raw: None,
    )
    assert paths == ["config.password"]
    assert "password" not in redacted