"""Shared domain kernel for external_systems (credential mode, purposes, ports)."""

from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.domain.ports import UserIntegrationAuthPort
from apps.shared.external_systems.domain.types import (
    CREDENTIAL_MODE_SHARED,
    CREDENTIAL_MODE_USER,
    USER_CONNECTION_CONNECTED,
    USER_CONNECTION_EXPIRED,
    USER_CONNECTION_NOT_CONNECTED,
    CredentialMode,
    CredentialModeStr,
    IntegrationPurpose,
    ResourceKind,
    UserConnectionStatus,
    UserConnectionStatusStr,
    effective_credential_mode,
)

__all__ = [
    "CREDENTIAL_MODE_SHARED",
    "CREDENTIAL_MODE_USER",
    "RESOURCE_TYPE_API_CONNECTOR",
    "RESOURCE_TYPE_DATA_SOURCE",
    "USER_CONNECTION_CONNECTED",
    "USER_CONNECTION_EXPIRED",
    "USER_CONNECTION_NOT_CONNECTED",
    "CredentialMode",
    "CredentialModeStr",
    "IntegrationPurpose",
    "ResourceKind",
    "UserConnectionStatus",
    "UserConnectionStatusStr",
    "UserIntegrationAuthPort",
    "effective_credential_mode",
]
