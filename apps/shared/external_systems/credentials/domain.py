"""Domain types for user credential bindings (BYOT / per-user integrations).

credential_mode (on data_sources / api_connectors) answers *who* supplies secrets:
  shared — tenant-wide config on the integration record
  user   — each member stores secrets in user_integration_credentials

auth_type is separate: it describes *how* credentials are shaped and applied.
  - Data sources: user row auth_type is db_password | pat (not HTTP).
  - API connectors: admin sets auth_type on the connector (HTTP scheme); per-user
    bindings use the same value and must match it on upsert (see user_integration_auth).

Canonical connector HTTP auth literals also live in apps.shared.api_connector.constants;
they are duplicated here as AUTH_TYPE_* to avoid import cycles from credentials → api_connector.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.domain.types import (
    CREDENTIAL_MODE_SHARED,
    CREDENTIAL_MODE_USER,
    CredentialMode,
    IntegrationPurpose,
    ResourceKind,
)

# user_integration_credentials.auth_type when resource_type = data_source
DataSourceUserCredentialAuthTypeStr: TypeAlias = Literal["db_password", "pat"]

# user_integration_credentials.auth_type when resource_type = api_connector (BYOT subset only)
ApiConnectorUserCredentialAuthTypeStr: TypeAlias = Literal["api_key", "bearer", "basic"]

# api_connectors.auth_type — integration definition (admin); includes schemes without BYOT
ApiConnectorDefinitionAuthTypeStr: TypeAlias = Literal["none", "api_key", "bearer", "basic", "custom"]

CREDENTIAL_STATUS_ACTIVE = "active"
CREDENTIAL_STATUS_EXPIRED = "expired"
CREDENTIAL_STATUS_REVOKED = "revoked"

# Per-user (BYOT) auth_type values stored on user_integration_credentials.auth_type
USER_INTEGRATION_AUTH_DB_PASSWORD = "db_password"
USER_INTEGRATION_AUTH_PAT = "pat"

# Connector auth types (must match api_connector.constants; not imported to avoid cycles)
AUTH_TYPE_NONE = "none"
AUTH_TYPE_API_KEY = "api_key"
AUTH_TYPE_BEARER = "bearer"
AUTH_TYPE_BASIC = "basic"
AUTH_TYPE_CUSTOM = "custom"

DATA_SOURCE_USER_AUTH_TYPES = frozenset({USER_INTEGRATION_AUTH_DB_PASSWORD, USER_INTEGRATION_AUTH_PAT})
BYOT_CONNECTOR_AUTH_TYPES = frozenset({AUTH_TYPE_API_KEY, AUTH_TYPE_BEARER, AUTH_TYPE_BASIC})

__all__ = [
    "AUTH_TYPE_API_KEY",
    "AUTH_TYPE_BASIC",
    "AUTH_TYPE_BEARER",
    "AUTH_TYPE_CUSTOM",
    "AUTH_TYPE_NONE",
    "ApiConnectorDefinitionAuthTypeStr",
    "ApiConnectorUserCredentialAuthTypeStr",
    "BYOT_CONNECTOR_AUTH_TYPES",
    "CREDENTIAL_MODE_SHARED",
    "CREDENTIAL_MODE_USER",
    "CREDENTIAL_STATUS_ACTIVE",
    "CREDENTIAL_STATUS_EXPIRED",
    "CREDENTIAL_STATUS_REVOKED",
    "DATA_SOURCE_USER_AUTH_TYPES",
    "DataSourceUserCredentialAuthTypeStr",
    "RESOURCE_TYPE_API_CONNECTOR",
    "RESOURCE_TYPE_DATA_SOURCE",
    "USER_INTEGRATION_AUTH_DB_PASSWORD",
    "USER_INTEGRATION_AUTH_PAT",
    "CredentialMode",
    "IntegrationPurpose",
    "ResourceKind",
]
