"""DTOs for document source sync APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GoogleDriveSourceConfigRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(
        default="",
        description="Send empty string on update to keep previous value.",
    )
    enabled: bool = False


class GoogleDriveSourceConfigResponse(BaseModel):
    provider: str = "google_drive"
    enabled: bool
    client_id: str | None = None
    client_secret_configured: bool = False


class DriveAuthorizeResponse(BaseModel):
    authorize_url: str


class DrivePickerConfigResponse(BaseModel):
    client_id: str
    access_token: str
    app_id: str


class DocumentSourceConnectionResponse(BaseModel):
    id: int
    provider_id: int
    provider: str
    account_email: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class CreateSyncConnectorRequest(BaseModel):
    source_connection_id: int
    source_folder_id: str = Field(..., min_length=1, max_length=128)
    source_folder_name: str = Field(..., min_length=1, max_length=500)
    include_subfolders: bool = True


class SyncConnectorResponse(BaseModel):
    id: int
    source_connection_id: int
    collection_id: int
    source_folder_id: str
    source_folder_name: str
    include_subfolders: bool
    status: str
    last_synced_at: datetime | None
    last_sync_error: str | None
    connection_owner_id: int
    connection_owner_username: str | None = None
    account_email: str | None = None
    created_at: datetime
    updated_at: datetime


class SyncConnectorResultResponse(BaseModel):
    connector_id: int
    added: int
    updated: int
    deleted: int
    skipped: int
