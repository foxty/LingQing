"""API connector module exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.shared.external_systems.api_connector.execution import ApiConnectorExecutionService, ApiExecutionResult
from apps.shared.external_systems.api_connector.repository import ApiConnectorRepository, ApiOperationIndexRepository

if TYPE_CHECKING:
    from apps.shared.external_systems.api_connector.service import ApiConnectorService

__all__ = [
    "ApiConnectorExecutionService",
    "ApiExecutionResult",
    "ApiConnectorRepository",
    "ApiOperationIndexRepository",
    "ApiConnectorService",
]


def __getattr__(name: str):
    if name == "ApiConnectorService":
        from apps.shared.external_systems.api_connector.service import ApiConnectorService

        return ApiConnectorService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")