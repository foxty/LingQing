"""DTOs for data_source module."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
)
from apps.shared.domain.value_objects import (
    AssetType,
    AssetTypeStr,
    DataSourceTypeStr,
)
from apps.shared.schemas.pagination import PaginatedResponse


class RAGSourceType(StrEnum):
    """RAG content source types for vector store filtering."""

    DOCUMENT = RESOURCE_TYPE_DOCUMENT  # File-based documents (PDF, Word, etc.)
    ASSET = RESOURCE_TYPE_ASSET  # Canonical asset source type for vector store filtering
    API_CONNECTOR = RESOURCE_TYPE_API_CONNECTOR  # API operation metadata source type


class DataSourceCreate(BaseModel):
    """Data source creation request."""

    name: str = Field(..., min_length=1, max_length=200, description="Data source name")
    type: DataSourceTypeStr = Field(..., description="Database type (sqlite, postgres, mysql, etc.)")
    managed: bool = Field(default=True, description="Whether this data source is managed by the platform")
    config: dict[str, Any] | None = Field(default=None, description="Data source configuration")
    description: str | None = Field(default=None, description="Data source description")


class DataSourceUpdate(BaseModel):
    """Data source update request."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    config: dict[str, Any] | None = None


class DataSourceResponse(BaseModel):
    """Data source response."""

    id: int
    tenant_id: int
    name: str
    type: str
    managed: bool
    config: dict[str, Any]
    description: str | None
    owner_name: str | None = Field(default=None, description="Canonical owner username")
    created_at: datetime
    updated_at: datetime
    asset_count: int = Field(default=0, description="Number of assets in this data source")

    model_config = ConfigDict(from_attributes=True)


class DataSourceListResponse(PaginatedResponse[DataSourceResponse]):
    """Paginated data source list response."""


class TestConnectionRequest(BaseModel):
    """Test connection request."""

    type: DataSourceTypeStr = Field(..., description="Database type")
    config: dict[str, Any] = Field(..., description="Connection configuration")


class TestConnectionResponse(BaseModel):
    """Test connection response."""

    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Success or error message")
    error: str | None = Field(default=None, description="Detailed error message if failed")
    details: dict[str, Any] | None = Field(default=None, description="Additional connection details")


class DiscoveredColumn(BaseModel):
    """Discovered column metadata from data source."""

    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Normalized data type (e.g., 'INTEGER', 'TEXT')")
    comment: str | None = Field(default=None, description="Column comment/description")


class DiscoveredAsset(BaseModel):
    """Discovered asset from data source."""

    name: str = Field(..., description="Asset name (table/view name)")
    type: AssetTypeStr = Field(..., description="Asset type (table/view)")
    row_count: int | None = Field(default=None, description="Number of rows")
    columns: list[DiscoveredColumn] | None = Field(default=None, description="Column information")
    description: str | None = Field(default=None, description="Asset description")


class DiscoveredAssetLight(BaseModel):
    """Lightweight discovered asset (no schema metadata)."""

    name: str = Field(..., description="Asset name (table/view name)")
    type: AssetTypeStr = Field(..., description="Asset type (table/view)")
    description: str | None = Field(default=None, description="Asset description")


class DiscoverAssetsRequest(BaseModel):
    """Discover assets request."""

    type: DataSourceTypeStr = Field(..., description="Database type")
    config: dict[str, Any] = Field(..., description="Connection configuration")


class DiscoverAssetsResponse(BaseModel):
    """Discover assets response."""

    assets: list[DiscoveredAsset] = Field(..., description="List of discovered assets")
    total: int = Field(..., description="Total number of assets")
    requires_query: bool = Field(
        default=False,
        description="True when the engine will not list assets until the caller searches",
    )


class DiscoverAssetsLightResponse(BaseModel):
    """Discover assets (light) response."""

    assets: list[DiscoveredAssetLight] = Field(..., description="List of discovered assets")
    total: int = Field(..., description="Total number of assets")


# ============ Asset Metadata Schemas ============


class AssetMetadataCreate(BaseModel):
    """Asset metadata creation request."""

    asset_name: str = Field(..., min_length=1, max_length=200, description="Asset name (table/view name)")
    asset_type: AssetTypeStr = Field(default=AssetType.TABLE, description="Asset type")
    columns: list[dict[str, Any]] = Field(default_factory=list, description="Column definitions")
    row_count: int | None = Field(default=None, description="Number of rows")
    source_info: dict[str, Any] = Field(default_factory=dict, description="Source information")
    meta: dict[str, Any] | None = Field(default=None, description="Synced metadata payload")


class AssetMetadataOverrideUpdate(BaseModel):
    """Asset metadata override update request (user edits)."""

    description: str | None = None
    column_description: dict[str, str | None] | None = None


class AssetMetadataResponse(BaseModel):
    """Asset metadata response."""

    id: int
    data_source_id: int
    asset_name: str
    asset_type: AssetTypeStr
    columns: list[dict[str, Any]]
    row_count: int | None
    source_info: dict[str, Any]
    meta: dict[str, Any] | None = None
    meta_override: dict[str, Any] | None = None
    owner_name: str | None = Field(
        default=None,
        description="Canonical owner username (fallback: 已删除用户 when owner is missing)",
    )
    created_at: datetime
    updated_at: datetime
    last_metadata_synced_at: datetime | None = Field(
        default=None, description="Last successful metadata sync from source database"
    )
    last_metadata_sync_error: str | None = Field(default=None, description="Last metadata sync error message")
    # Vector sync status fields from ResourceIndex
    last_vector_synced_at: datetime | None = Field(
        default=None, description="Last successful vector sync to search index"
    )
    last_vector_sync_error: str | None = Field(default=None, description="Last vector sync error message")

    model_config = ConfigDict(from_attributes=True)


class AssetQueryRequest(BaseModel):
    """Asset query request."""

    sql: str | None = Field(default=None, description="SQL query (optional, returns all if not provided)")
    limit: int = Field(default=100, ge=1, le=10000, description="Row limit")


class DataSourceQueryRequest(BaseModel):
    """Data source SQL query request."""

    sql: str = Field(..., min_length=1, description="Read-only SQL query")
    limit: int = Field(default=200, ge=1, le=10000, description="Maximum rows to return")


class AssetSchemaResponse(BaseModel):
    """Asset schema response."""

    asset_name: str
    asset_type: AssetTypeStr
    columns: list[dict[str, Any]]
    row_count: int | None
    data_source_id: int
