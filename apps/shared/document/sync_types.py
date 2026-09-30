"""Domain types and constants for external document source sync."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

ConnectionStatus = Literal["active", "revoked"]
ConnectorStatus = Literal["active", "stopped"]


class DocumentSourceProviderKey(StrEnum):
    GOOGLE_DRIVE = "google_drive"


DEFAULT_DOCUMENT_SOURCE_PROVIDER = DocumentSourceProviderKey.GOOGLE_DRIVE

SENSITIVE_PROVIDER_CONFIG_FIELDS = frozenset({"client_secret"})
SENSITIVE_CONNECTION_CREDENTIAL_FIELDS = frozenset({"access_token", "refresh_token"})
