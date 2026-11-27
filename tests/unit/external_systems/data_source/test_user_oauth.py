"""Unit tests for Databricks per-user OAuth config on data sources."""

from __future__ import annotations

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.external_systems.data_source.config_secrets_policy import prepare_data_source_config_for_storage
from apps.shared.external_systems.data_source.user_oauth import (
    USER_CREDENTIAL_AUTH_OAUTH2,
    USER_OAUTH_CONFIG_KEY,
    databricks_oidc_urls,
    merge_user_oauth_into_config,
    oauth_client_fields_from_data_source_config,
    oauth_token_refresh_template,
    user_credential_auth_type_from_config,
    validate_databricks_user_oauth_settings,
)
from apps.shared.utils.field_cipher import FieldCipher

_CIPHER_KEY = "synthetic-ds-oauth-config-key"


def _oauth_block(*, include_urls: bool = True) -> dict:
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    block = {
        "client_id": "synthetic-client",
        "client_secret": "synthetic-secret",
        "redirect_uri": "https://api.example.test/integrations/oauth/callback",
    }
    if include_urls:
        block["authorize_url"] = auth
        block["token_url"] = token
    block.setdefault("scopes", ["sql:read:restricted-query", "offline_access"])
    return block


def _valid_oauth_config(cipher: FieldCipher) -> dict:
    return {
        "host": "adb-example.azuredatabricks.net",
        "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
        USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
            {**_oauth_block(), "scopes": ["sql", "offline_access"]},
            sensitive_fields={"client_secret"},
        ),
    }


def test_oauth_client_fields_rejects_empty_scopes():
    cipher = FieldCipher(_CIPHER_KEY)
    block = {**_oauth_block(), "scopes": []}
    config = {
        "host": "adb-example.azuredatabricks.net",
        USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
            block,
            sensitive_fields={"client_secret"},
        ),
    }
    with pytest.raises(ValidationError, match="at least one authorize scope"):
        oauth_client_fields_from_data_source_config(config, cipher=cipher)


def test_user_credential_auth_type_from_config_defaults_pat():
    assert user_credential_auth_type_from_config({}) == "pat"
    assert (
        user_credential_auth_type_from_config({"user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2})
        == USER_CREDENTIAL_AUTH_OAUTH2
    )


def test_databricks_oidc_urls_from_host():
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    assert auth.endswith("/oidc/v1/authorize")
    assert token.endswith("/oidc/v1/token")


def test_databricks_oidc_urls_rejects_empty_host():
    with pytest.raises(ValidationError, match="host"):
        databricks_oidc_urls("   ")


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {
                "data_source_type": "postgres",
                "credential_mode": "user",
                "managed": False,
                "config": {
                    "host": "h",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: _oauth_block(),
                },
            },
            "Databricks",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "user",
                "managed": True,
                "config": {
                    "host": "h",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: _oauth_block(),
                },
            },
            "Managed",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "shared",
                "managed": False,
                "config": {
                    "host": "h",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: _oauth_block(),
                },
            },
            "credential_mode=user",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "user",
                "managed": False,
                "config": {
                    "host": "",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: _oauth_block(),
                },
            },
            "host",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "user",
                "managed": False,
                "config": {
                    "host": "adb-example.azuredatabricks.net",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: {},
                },
            },
            "client_id",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "user",
                "managed": False,
                "config": {
                    "host": "adb-example.azuredatabricks.net",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: {
                        **_oauth_block(include_urls=False),
                        "client_id": "c",
                    },
                },
            },
            "authorize_url",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "user",
                "managed": False,
                "config": {
                    "host": "adb-example.azuredatabricks.net",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: {
                        "client_id": "c",
                        "authorize_url": "https://adb/oidc/v1/authorize",
                        "token_url": "https://adb/oidc/v1/token",
                    },
                },
            },
            "redirect_uri",
        ),
        (
            {
                "data_source_type": "databricks",
                "credential_mode": "user",
                "managed": False,
                "config": {
                    "host": "adb-example.azuredatabricks.net",
                    "user_credential_auth_type": USER_CREDENTIAL_AUTH_OAUTH2,
                    USER_OAUTH_CONFIG_KEY: {
                        **_oauth_block(),
                        "scopes": [],
                    },
                },
            },
            "at least one authorize scope",
        ),
    ],
)
def test_validate_databricks_user_oauth_settings_rejects_invalid_config(kwargs, match):
    with pytest.raises(ValidationError, match=match):
        validate_databricks_user_oauth_settings(**kwargs)


def test_validate_databricks_user_oauth_skips_when_auth_type_pat():
    validate_databricks_user_oauth_settings(
        data_source_type="postgres",
        credential_mode="shared",
        managed=True,
        config={},
    )


def test_oauth_client_fields_requires_persisted_oauth_endpoints():
    cipher = FieldCipher(_CIPHER_KEY)
    config = _valid_oauth_config(cipher)
    oauth = oauth_client_fields_from_data_source_config(config, cipher=cipher)
    assert oauth["client_id"] == "synthetic-client"
    assert oauth["client_secret"] == "synthetic-secret"
    assert oauth["redirect_uri"] == "https://api.example.test/integrations/oauth/callback"
    assert "sql" in oauth["scopes"]


def test_oauth_client_fields_rejects_omitted_scopes():
    cipher = FieldCipher(_CIPHER_KEY)
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    config = {
        "host": "adb-example.azuredatabricks.net",
        USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
            {
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
                "authorize_url": auth,
                "token_url": token,
                "redirect_uri": "https://api.example.test/integrations/oauth/callback",
            },
            sensitive_fields={"client_secret"},
        ),
    }
    with pytest.raises(ValidationError, match="at least one authorize scope"):
        oauth_client_fields_from_data_source_config(config, cipher=cipher)


def test_oauth_client_fields_preserves_explicit_restricted_scope():
    cipher = FieldCipher(_CIPHER_KEY)
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    config = {
        "host": "adb-example.azuredatabricks.net",
        USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
            {
                **_oauth_block(),
                "scopes": ["sql:read:restricted-query", "offline_access"],
            },
            sensitive_fields={"client_secret"},
        ),
    }
    oauth = oauth_client_fields_from_data_source_config(config, cipher=cipher)
    assert oauth["scopes"] == ["sql:read:restricted-query", "offline_access"]


def test_oauth_client_fields_rejects_missing_redirect_uri():
    cipher = FieldCipher(_CIPHER_KEY)
    auth, token = databricks_oidc_urls("adb-example.azuredatabricks.net")
    config = {
        "host": "adb-example.azuredatabricks.net",
        USER_OAUTH_CONFIG_KEY: cipher.encrypt_dict(
            {
                "client_id": "synthetic-client",
                "client_secret": "synthetic-secret",
                "authorize_url": auth,
                "token_url": token,
                "scopes": ["sql:read:restricted-query"],
            },
            sensitive_fields={"client_secret"},
        ),
    }
    with pytest.raises(ValidationError, match="redirect_uri"):
        oauth_client_fields_from_data_source_config(config, cipher=cipher)


def test_oauth_token_refresh_template_shape():
    cipher = FieldCipher(_CIPHER_KEY)
    template = oauth_token_refresh_template(_valid_oauth_config(cipher), cipher=cipher)
    assert template["client_id"] == "synthetic-client"
    assert template["client_secret"] == "synthetic-secret"
    assert template["token_url"].endswith("/oidc/v1/token")


def test_prepare_data_source_config_encrypts_client_secret():
    cipher = FieldCipher(_CIPHER_KEY)
    stored = prepare_data_source_config_for_storage(
        {
            "host": "adb-example.azuredatabricks.net",
            USER_OAUTH_CONFIG_KEY: {"client_id": "c", "client_secret": "plain-secret"},
        },
        cipher=cipher,
    )
    secret = stored[USER_OAUTH_CONFIG_KEY]["client_secret"]
    assert secret.startswith("enc:")
    assert cipher.decrypt(secret) == "plain-secret"


def test_merge_user_oauth_preserves_client_secret_when_omitted_on_patch():
    cipher = FieldCipher(_CIPHER_KEY)
    existing = prepare_data_source_config_for_storage(
        {
            USER_OAUTH_CONFIG_KEY: {
                "client_id": "c",
                "client_secret": "keep-me",
                "authorize_url": "https://a",
                "token_url": "https://t",
                "redirect_uri": "https://api/callback",
            },
        },
        cipher=cipher,
    )
    merged = merge_user_oauth_into_config(
        existing,
        {USER_OAUTH_CONFIG_KEY: {"client_id": "c-next"}},
        cipher=cipher,
    )
    assert merged[USER_OAUTH_CONFIG_KEY]["client_secret"] == "keep-me"
    assert merged[USER_OAUTH_CONFIG_KEY]["client_id"] == "c-next"