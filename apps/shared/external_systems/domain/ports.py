"""Ports for per-user integration credentials (BYOT). Infrastructure implements; consumers depend on the port only."""

from __future__ import annotations

from typing import Any, Protocol

from apps.shared.domain.actor import ActorContext


class UserIntegrationAuthPort(Protocol):
    """Resolve per-user credentials for BYOT integrations.

    ``IntegrationCredentialResolver`` implements both methods. Api connector *execution* depends on
    this port for custom session auth; data-source query paths call the same resolver from
    ``DataSourceService`` (warehouse managers), not through this port type today.
    """

    async def resolve_data_source_config(
        self,
        *,
        data_source: Any,
        actor: ActorContext | None,
        purpose: str,
    ) -> dict[str, Any]: ...

    async def resolve_api_connector_auth_config(
        self,
        *,
        connector: Any,
        actor: ActorContext | None,
        purpose: str,
    ) -> dict[str, Any]: ...
