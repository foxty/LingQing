"""Unit tests for BYOT auth_type and secret shape validation."""

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.domain.value_objects import DataSourceType
from apps.shared.external_systems.api_connector.constants import AUTH_TYPE_BEARER, AUTH_TYPE_NONE
from apps.shared.external_systems.credentials.domain import (
    USER_INTEGRATION_AUTH_DB_PASSWORD,
    USER_INTEGRATION_AUTH_PAT,
)
from apps.shared.external_systems.credentials.user_integration_auth import (
    expected_data_source_user_auth_type,
    validate_data_source_user_integration,
    validate_api_connector_user_integration,
    validate_merged_secrets_for_auth_type,
)


def test_expected_auth_type_for_rdbms_vs_databricks():
    assert expected_data_source_user_auth_type("postgres") == USER_INTEGRATION_AUTH_DB_PASSWORD
    assert expected_data_source_user_auth_type(DataSourceType.DATABRICKS) == USER_INTEGRATION_AUTH_PAT


def test_db_password_requires_username_and_password():
    validate_merged_secrets_for_auth_type(
        USER_INTEGRATION_AUTH_DB_PASSWORD,
        {"username": "u", "password": "p"},
    )
    with pytest.raises(ValidationError, match="username and password"):
        validate_merged_secrets_for_auth_type(USER_INTEGRATION_AUTH_DB_PASSWORD, {"username": "u"})


def test_pat_requires_token_field():
    validate_merged_secrets_for_auth_type(USER_INTEGRATION_AUTH_PAT, {"password": "tok"})
    with pytest.raises(ValidationError, match="token"):
        validate_merged_secrets_for_auth_type(USER_INTEGRATION_AUTH_PAT, {})


def test_data_source_rejects_wrong_auth_type_for_postgres():
    with pytest.raises(ValidationError, match="db_password"):
        validate_data_source_user_integration(
            data_source_type="postgres",
            auth_type=USER_INTEGRATION_AUTH_PAT,
            merged_secrets={"password": "x"},
        )


def test_api_connector_auth_type_must_match_connector():
    validate_api_connector_user_integration(
        connector_auth_type=AUTH_TYPE_BEARER,
        auth_type=AUTH_TYPE_BEARER,
        merged_secrets={"token": "abc"},
    )
    with pytest.raises(ValidationError, match="must match"):
        validate_api_connector_user_integration(
            connector_auth_type=AUTH_TYPE_BEARER,
            auth_type="api_key",
            merged_secrets={"api_key": "k"},
        )


def test_api_connector_rejects_none_auth_on_connector():
    with pytest.raises(ValidationError, match="not supported"):
        validate_api_connector_user_integration(
            connector_auth_type=AUTH_TYPE_NONE,
            auth_type=AUTH_TYPE_NONE,
            merged_secrets={},
        )
