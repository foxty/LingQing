"""Cross-cutting types for external system integrations (shared vs user credentials, purposes)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, TypeAlias

from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE

CREDENTIAL_MODE_SHARED = "shared"
CREDENTIAL_MODE_USER = "user"

CredentialModeStr: TypeAlias = Literal["shared", "user"]

USER_CONNECTION_NOT_CONNECTED = "not_connected"
USER_CONNECTION_CONNECTED = "connected"
USER_CONNECTION_EXPIRED = "expired"

UserConnectionStatusStr: TypeAlias = Literal["not_connected", "connected", "expired"]


class CredentialMode(StrEnum):
    SHARED = CREDENTIAL_MODE_SHARED
    USER = CREDENTIAL_MODE_USER


class UserConnectionStatus(StrEnum):
    NOT_CONNECTED = USER_CONNECTION_NOT_CONNECTED
    CONNECTED = USER_CONNECTION_CONNECTED
    EXPIRED = USER_CONNECTION_EXPIRED


class ResourceKind(StrEnum):
    DATA_SOURCE = RESOURCE_TYPE_DATA_SOURCE
    API_CONNECTOR = RESOURCE_TYPE_API_CONNECTOR


class IntegrationPurpose(StrEnum):
    QUERY = "query"
    EXECUTE = "execute"
    DISCOVER = "discover"


def effective_credential_mode(mode: str | None) -> CredentialModeStr:
    """Normalize persisted/API credential_mode to a known value."""
    if mode == CREDENTIAL_MODE_USER:
        return CREDENTIAL_MODE_USER
    return CREDENTIAL_MODE_SHARED
