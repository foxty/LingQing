"""Validation for per-user integration credential auth_type and secret shape.

credential_mode is not validated here (callers enforce BYOT on the integration record).

For API connectors, validate_api_connector_user_integration takes two auth_type values:
  connector_auth_type — from api_connectors.auth_type (admin contract)
  auth_type           — from the upsert body / user_integration_credentials row

They must be equal for supported BYOT schemes; the user does not pick a different scheme.
"""

from __future__ import annotations

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.domain.value_objects import DataSourceType, DataSourceTypeStr
from apps.shared.external_systems.credentials.domain import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_CUSTOM,
    AUTH_TYPE_NONE,
    BYOT_CONNECTOR_AUTH_TYPES,
    DATA_SOURCE_USER_AUTH_TYPES,
    USER_INTEGRATION_AUTH_DB_PASSWORD,
    USER_INTEGRATION_AUTH_PAT,
    ApiConnectorDefinitionAuthTypeStr,
    ApiConnectorUserCredentialAuthTypeStr,
    DataSourceUserCredentialAuthTypeStr,
)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def expected_data_source_user_auth_type(
    data_source_type: DataSourceTypeStr | str,
) -> DataSourceUserCredentialAuthTypeStr:
    """Map warehouse engine type to the only allowed user credential auth_type."""
    if data_source_type == DataSourceType.DATABRICKS:
        return USER_INTEGRATION_AUTH_PAT
    return USER_INTEGRATION_AUTH_DB_PASSWORD


def validate_user_integration_auth_type_string(
    auth_type: str | DataSourceUserCredentialAuthTypeStr | ApiConnectorUserCredentialAuthTypeStr,
) -> None:
    if not auth_type or not auth_type.strip():
        raise ValidationError("auth_type is required")
    if len(auth_type) > 50:
        raise ValidationError("auth_type is too long")


def _require_keys(merged: dict[str, str], *keys: str, message: str) -> None:
    missing = [k for k in keys if not _non_empty(merged.get(k))]
    if missing:
        raise ValidationError(message)


def validate_merged_secrets_for_auth_type(
    auth_type: DataSourceUserCredentialAuthTypeStr | ApiConnectorUserCredentialAuthTypeStr | str,
    merged: dict[str, str],
) -> None:
    """Ensure merged plaintext secrets satisfy the declared auth_type."""
    if auth_type == USER_INTEGRATION_AUTH_PAT:
        _require_keys(merged, "password", message="Personal access token is required")
        return
    if auth_type == USER_INTEGRATION_AUTH_DB_PASSWORD:
        _require_keys(
            merged,
            "username",
            "password",
            message="Database username and password are required",
        )
        return
    if auth_type == AUTH_TYPE_API_KEY:
        _require_keys(merged, "api_key", message="API key value is required")
        return
    if auth_type == AUTH_TYPE_BEARER:
        _require_keys(merged, "token", message="Bearer token is required")
        return
    if auth_type == AUTH_TYPE_BASIC:
        _require_keys(merged, "username", "password", message="Username and password are required")
        return
    raise ValidationError(f"Unsupported auth_type: {auth_type}")


def validate_data_source_user_integration(
    *,
    data_source_type: DataSourceTypeStr | str,
    auth_type: DataSourceUserCredentialAuthTypeStr | str,
    merged_secrets: dict[str, str],
) -> None:
    """BYOT data source: auth_type is driven by data source engine type (db_password vs pat)."""
    validate_user_integration_auth_type_string(auth_type)
    if auth_type not in DATA_SOURCE_USER_AUTH_TYPES:
        raise ValidationError(
            f"auth_type must be one of: {', '.join(sorted(DATA_SOURCE_USER_AUTH_TYPES))}"
        )
    expected = expected_data_source_user_auth_type(data_source_type)
    if auth_type != expected:
        raise ValidationError(
            f"auth_type must be '{expected}' for data source type '{data_source_type}'"
        )
    validate_merged_secrets_for_auth_type(auth_type, merged_secrets)


def validate_api_connector_user_integration(
    *,
    connector_auth_type: ApiConnectorDefinitionAuthTypeStr | str,
    auth_type: ApiConnectorUserCredentialAuthTypeStr | str,
    merged_secrets: dict[str, str],
) -> None:
    """BYOT API connector: user auth_type must match the connector definition auth_type."""
    validate_user_integration_auth_type_string(auth_type)
    if connector_auth_type in (AUTH_TYPE_NONE, AUTH_TYPE_CUSTOM):
        raise ValidationError("Per-user credentials are not supported for this connector auth type")
    if connector_auth_type not in BYOT_CONNECTOR_AUTH_TYPES:
        raise ValidationError("Per-user credentials are not supported for this connector auth type")
    if auth_type != connector_auth_type:
        raise ValidationError("auth_type must match the connector authentication type")
    if auth_type not in BYOT_CONNECTOR_AUTH_TYPES:
        raise ValidationError(f"auth_type must be one of: {', '.join(sorted(BYOT_CONNECTOR_AUTH_TYPES))}")
    validate_merged_secrets_for_auth_type(auth_type, merged_secrets)


def validate_user_integration_upsert(
    *,
    resource_type: str,
    auth_type: DataSourceUserCredentialAuthTypeStr | ApiConnectorUserCredentialAuthTypeStr | str,
    merged_secrets: dict[str, str],
    data_source_type: DataSourceTypeStr | str | None = None,
    connector_auth_type: ApiConnectorDefinitionAuthTypeStr | str | None = None,
) -> None:
    if resource_type == RESOURCE_TYPE_DATA_SOURCE:
        if not data_source_type:
            raise ValidationError("data_source_type is required")
        validate_data_source_user_integration(
            data_source_type=data_source_type,
            auth_type=auth_type,
            merged_secrets=merged_secrets,
        )
        return
    if resource_type == RESOURCE_TYPE_API_CONNECTOR:
        if not connector_auth_type:
            raise ValidationError("connector_auth_type is required")
        validate_api_connector_user_integration(
            connector_auth_type=connector_auth_type,
            auth_type=auth_type,
            merged_secrets=merged_secrets,
        )
        return
    raise ValidationError(f"Unsupported resource_type: {resource_type}")
