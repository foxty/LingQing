"""HTTP contracts for integration-pack and connector sync-pack routes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.shared.external_systems.api_connector.schemas import ApiConnectorResponse, PackSyncSummaryDTO


class InstallApiConnectorPackRequest(BaseModel):
    pack_id: str
    client_id: str | None = Field(default=None, min_length=1)
    client_secret: str | None = Field(default=None, min_length=1)
    redirect_uri: str | None = None


class InstallApiConnectorPackResponse(BaseModel):
    connector: ApiConnectorResponse
    sync_summary: PackSyncSummaryDTO | None = None


class SyncPackResponse(BaseModel):
    connector: ApiConnectorResponse
    summary: PackSyncSummaryDTO