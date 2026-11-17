"""Domain types and constants for external document source sync."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

ConnectionStatus = Literal["active", "revoked"]
ConnectorStatus = Literal["active", "stopped"]


class SourceConnectionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class DocumentSyncConnectorStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"


SOURCE_CONNECTION_ACTIVE: Final = SourceConnectionStatus.ACTIVE.value
SOURCE_CONNECTION_REVOKED: Final = SourceConnectionStatus.REVOKED.value
CONNECTOR_ACTIVE: Final = DocumentSyncConnectorStatus.ACTIVE.value
CONNECTOR_STOPPED: Final = DocumentSyncConnectorStatus.STOPPED.value


class DocumentSourceProviderKey(StrEnum):
    GOOGLE_DRIVE = "google_drive"


DEFAULT_DOCUMENT_SOURCE_PROVIDER = DocumentSourceProviderKey.GOOGLE_DRIVE

SENSITIVE_PROVIDER_CONFIG_FIELDS = frozenset({"client_secret"})
SENSITIVE_CONNECTION_CREDENTIAL_FIELDS = frozenset({"access_token", "refresh_token"})
