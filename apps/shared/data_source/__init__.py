"""Data Source module.

External modules should only import the service layer and public DTOs.
Internal implementation details are hidden.
"""

from apps.shared.data_source.domain import AssetMetadataDomain, DataSourceDomain
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.data_source.schemas import (
    AssetMetadataCreate,
    AssetMetadataOverrideUpdate,
    AssetMetadataResponse,
    AssetQueryRequest,
    AssetSchemaResponse,
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
    DiscoverAssetsRequest,
    DiscoverAssetsResponse,
    DiscoveredAsset,
    DiscoveredColumn,
    TestConnectionRequest,
    TestConnectionResponse,
)
from apps.shared.data_source.service import DataSourceService
from apps.shared.data_source.temp_table_repository import TempTableRepository


# Lazy import to avoid circular dependency with search module
def __getattr__(name: str):
    if name == "AssetMetadataService":
        from apps.shared.data_source.asset_metadata_service import AssetMetadataService

        return AssetMetadataService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DataSourceService",
    "AssetMetadataService",
    "DataSourceRepository",
    "AssetMetadataRepository",
    "TempTableRepository",
    "DataSourceDomain",
    "AssetMetadataDomain",
    "DataSourceCreate",
    "DataSourceUpdate",
    "DataSourceResponse",
    "DataSourceListResponse",
    "TestConnectionRequest",
    "TestConnectionResponse",
    "DiscoveredAsset",
    "DiscoveredColumn",
    "DiscoverAssetsRequest",
    "DiscoverAssetsResponse",
    "AssetMetadataCreate",
    "AssetMetadataOverrideUpdate",
    "AssetMetadataResponse",
    "AssetQueryRequest",
    "AssetSchemaResponse",
]
