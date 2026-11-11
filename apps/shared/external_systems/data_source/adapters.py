"""Adapters for DataSource and AssetMetadata domain model conversions."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from apps.shared.db import models as db_models
from apps.shared.domain.value_objects import AssetMetaVO, ColumnVO, DatabaseConnectionVO
from apps.shared.external_systems.data_source.catalog_sync import (
    API_SECRET_PLACEHOLDER,
    METADATA_SYNC_CONFIG_KEY,
    CatalogSyncCredentials,
)
from apps.shared.external_systems.data_source.domain import AssetMetadataDomain, DataSourceDomain
from apps.shared.external_systems.data_source.schemas import (
    AssetMetadataCreate,
    AssetMetadataResponse,
    AssetSchemaResponse,
    DataSourceCreate,
    DataSourceResponse,
    DiscoveredAsset,
)
from apps.shared.external_systems.domain.types import effective_credential_mode

# ============ Domain to DTO Conversions ============


def discovered_asset_to_domain(
    discovered: DiscoveredAsset,
    data_source_id: int,
    owner_id: int,
) -> AssetMetadataDomain:
    """Convert DiscoveredAsset DTO to AssetMetadataDomain (factory adapter).

    This adapter combines DTO-to-Domain conversion with domain factory logic.
    Used by API/Router layer to prepare domain objects before passing to services.

    Args:
        discovered: Discovered asset DTO from external source
        data_source_id: Data source ID
        owner_id: Canonical owner user ID
    Returns:
        New AssetMetadataDomain ready for persistence (id=None)
    """
    from apps.shared.domain.value_objects import ColumnVO, DataType

    column_vos = []
    if discovered.columns:
        for col in discovered.columns:
            column_vos.append(
                ColumnVO(
                    name=col.name,
                    data_type=DataType.from_sql_type(col.data_type),
                    raw_data_type=col.data_type,  # Preserve raw external type
                )
            )

    meta = AssetMetaVO(
        description=discovered.description,
        column_description={col.name: col.comment for col in discovered.columns or [] if col.comment},
    )
    return AssetMetadataDomain.create_new(
        data_source_id=data_source_id,
        asset_name=discovered.name,
        asset_type=discovered.type,
        columns=column_vos,
        row_count=discovered.row_count,
        source_info={},
        meta=meta,
        owner_id=owner_id,
    )


# ============ DB Conversions - DataSource ============


def _connection_vo_from_config(connection: DatabaseConnectionVO | Mapping[str, Any]) -> DatabaseConnectionVO:
    if isinstance(connection, DatabaseConnectionVO):
        return connection
    return DatabaseConnectionVO.from_dict(dict(connection))


def db_data_source_to_domain_with_connection(
    entity: db_models.DataSource,
    connection: DatabaseConnectionVO | Mapping[str, Any],
) -> DataSourceDomain:
    """Map a persisted data source using a resolved or merged connection config."""
    domain = db_data_source_to_domain(entity)
    if domain is None:
        raise ValueError(f"Data source {entity.id} not found")
    return DataSourceDomain(
        id=domain.id,
        tenant_id=domain.tenant_id,
        name=domain.name,
        type=domain.type,
        managed=domain.managed,
        connection=_connection_vo_from_config(connection),
        description=domain.description,
        owner_id=domain.owner_id,
        owner_name=domain.owner_name,
        asset_count=domain.asset_count,
        credential_mode=domain.credential_mode,
        catalog_sync=domain.catalog_sync,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        assets=domain.assets,
    )


def redact_data_source_config_for_api(config: dict[str, Any] | None) -> dict[str, Any]:
    """Presentation mapping: secrets in stored config → API placeholder."""
    if not config:
        return {}
    out = deepcopy(config)
    sync = out.get(METADATA_SYNC_CONFIG_KEY)
    if isinstance(sync, dict) and sync.get("password"):
        sync["password"] = API_SECRET_PLACEHOLDER
    if out.get("password"):
        out["password"] = API_SECRET_PLACEHOLDER
    return out


def db_data_source_to_api_response(
    entity: db_models.DataSource,
    *,
    api_config: dict[str, Any],
) -> DataSourceResponse:
    """Map DB entity to API response using the supplied config payload."""
    domain = db_data_source_to_domain(entity)
    if domain is None:
        raise ValueError(f"Data source {entity.id} not found")
    return domain_data_source_to_api(domain, raw_config=api_config)


def db_data_source_to_public_api_response(entity: db_models.DataSource) -> DataSourceResponse:
    """DB entity → public ``DataSourceResponse`` with config redacted."""
    return db_data_source_to_api_response(
        entity,
        api_config=redact_data_source_config_for_api(entity.config or {}),
    )


def db_data_source_to_domain(db_ds: db_models.DataSource | None) -> DataSourceDomain | None:
    """Convert DB DataSource to Domain DataSource.

    Args:
        db_ds: DB DataSource model with optional preloaded assets relationship

    Returns:
        DataSourceDomain with populated assets list, or None if db_ds is None
    """
    if not db_ds:
        return None

    # Convert preloaded assets if available
    assets = []
    if hasattr(db_ds, "assets") and db_ds.assets:
        assets = [db_asset_metadata_to_domain(asset) for asset in db_ds.assets if asset]

    return DataSourceDomain(
        id=db_ds.id,
        tenant_id=db_ds.tenant_id,
        name=db_ds.name,
        type=db_ds.type,
        managed=db_ds.managed,
        connection=DatabaseConnectionVO.from_dict(db_ds.config),
        description=db_ds.description,
        owner_id=db_ds.owner_id,
        owner_name=(db_ds.owner_user.username if db_ds.owner_user else None),
        asset_count=db_ds.asset_count,
        credential_mode=effective_credential_mode(db_ds.credential_mode),
        catalog_sync=CatalogSyncCredentials.from_data_source_config(db_ds.config),
        created_at=db_ds.created_at,
        updated_at=db_ds.updated_at,
        assets=assets,
    )


def domain_data_source_to_db_dict(domain_ds: DataSourceDomain) -> dict:
    """Convert Domain DataSource to dict for DB operations."""
    return {
        "tenant_id": domain_ds.tenant_id,
        "name": domain_ds.name,
        "type": domain_ds.type,
        "managed": domain_ds.managed,
        "config": domain_ds.connection.to_dict(),
        "description": domain_ds.description,
        "owner_id": domain_ds.owner_id,
        "credential_mode": domain_ds.credential_mode,
    }


# ============ DB Conversions - AssetMetadata ============


def db_asset_metadata_to_domain(
    db_asset: db_models.AssetMetadata,
    resource_index: db_models.ResourceIndex | None = None,
) -> AssetMetadataDomain:
    """Convert DB AssetMetadata to Domain AssetMetadata.

    Args:
        db_asset: AssetMetadata DB model
        resource_index: Optional ResourceIndex for sync status
    """
    meta = AssetMetaVO.from_dict(db_asset.meta)
    meta_override = AssetMetaVO.from_dict(db_asset.meta_override)
    columns = []
    for col in db_asset.columns:
        columns.append(ColumnVO.from_dict(col))

    return AssetMetadataDomain(
        data_source_id=db_asset.data_source_id,
        asset_name=db_asset.asset_name,
        asset_type=db_asset.asset_type,
        columns=columns,
        row_count=db_asset.row_count,
        source_info=db_asset.source_info,
        meta=meta,
        meta_override=meta_override,
        created_at=db_asset.created_at,
        updated_at=db_asset.updated_at,
        owner_id=db_asset.owner_id,
        owner_name=(db_asset.owner_user.username if db_asset.owner_user else None),
        id=db_asset.id,
        last_metadata_synced_at=db_asset.last_metadata_synced_at,
        last_metadata_sync_error=db_asset.last_metadata_sync_error,
        vector_synced_at=resource_index.vector_synced_at if resource_index else None,
        vector_sync_error=resource_index.vector_sync_error if resource_index else None,
        vector_sync_error_at=resource_index.vector_sync_error_at if resource_index else None,
    )


def domain_asset_metadata_to_db_model(domain_asset: AssetMetadataDomain) -> db_models.AssetMetadata:
    return db_models.AssetMetadata(
        data_source_id=domain_asset.data_source_id,
        asset_name=domain_asset.asset_name,
        asset_type=str(domain_asset.asset_type),  # Convert enum to string
        columns=[col.to_dict() for col in domain_asset.columns],
        row_count=domain_asset.row_count,
        source_info=domain_asset.source_info,
        meta=domain_asset.meta.to_dict(),
        meta_override=domain_asset.meta_override.to_dict(),
        owner_id=domain_asset.owner_id,
        last_metadata_synced_at=domain_asset.last_metadata_synced_at,
        last_metadata_sync_error=domain_asset.last_metadata_sync_error,
    )


# ============ API Conversions - DataSource ============


def api_data_source_create_to_domain(
    api_create: DataSourceCreate,
    tenant_id: int,
    owner_id: int,
) -> DataSourceDomain:
    """Convert API DataSourceCreate to Domain DataSource."""
    return DataSourceDomain(
        id=0,
        tenant_id=tenant_id,
        name=api_create.name,
        type=api_create.type,
        managed=api_create.managed,
        connection=DatabaseConnectionVO.from_dict(api_create.config or {}),
        description=api_create.description,
        owner_id=owner_id,
        owner_name=None,
        asset_count=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def domain_data_source_to_api(
    domain_ds: DataSourceDomain,
    *,
    raw_config: dict | None = None,
) -> DataSourceResponse:
    """Convert Domain DataSource to API DataSourceResponse."""
    config_payload = raw_config if raw_config is not None else domain_ds.connection.to_dict()
    return DataSourceResponse(
        id=domain_ds.id,
        tenant_id=domain_ds.tenant_id,
        name=domain_ds.name,
        type=domain_ds.type,
        managed=domain_ds.managed,
        config=config_payload,
        asset_count=domain_ds.asset_count,
        description=domain_ds.description,
        owner_name=domain_ds.owner_name,
        credential_mode=effective_credential_mode(domain_ds.credential_mode),
        user_connection_status=None,
        created_at=domain_ds.created_at,
        updated_at=domain_ds.updated_at,
    )


# ============ API Conversions - AssetMetadata ============


def api_asset_create_to_domain(
    api_create: AssetMetadataCreate,
    data_source_id: int,
    owner_id: int,
) -> AssetMetadataDomain:
    """Convert API AssetMetadataCreate to Domain AssetMetadata."""
    columns = [ColumnVO.from_dict(col) for col in api_create.columns]
    meta = AssetMetaVO.from_dict(api_create.meta)
    return AssetMetadataDomain(
        data_source_id=data_source_id,
        asset_name=api_create.asset_name,
        asset_type=api_create.asset_type,
        columns=columns,
        row_count=api_create.row_count,
        source_info=api_create.source_info,
        meta=meta,
        meta_override=AssetMetaVO(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        owner_id=owner_id,
        id=None,
    )


def domain_asset_metadata_to_api(
    domain_asset: AssetMetadataDomain,
) -> AssetMetadataResponse:
    """Convert Domain AssetMetadata to API AssetMetadataResponse.

    Args:
        domain_asset: Asset metadata domain object with sync status fields
    """
    return AssetMetadataResponse(
        id=domain_asset.id,
        data_source_id=domain_asset.data_source_id,
        asset_name=domain_asset.asset_name,
        asset_type=domain_asset.asset_type,
        columns=domain_asset.resolved_columns(),
        row_count=domain_asset.row_count,
        source_info=domain_asset.source_info,
        meta=domain_asset.meta.to_dict(),
        meta_override=domain_asset.meta_override.to_dict(),
        owner_name=domain_asset.owner_name,
        created_at=domain_asset.created_at,
        updated_at=domain_asset.updated_at,
        last_metadata_synced_at=domain_asset.last_metadata_synced_at,
        last_metadata_sync_error=domain_asset.last_metadata_sync_error,
        last_vector_synced_at=domain_asset.vector_synced_at,
        last_vector_sync_error=domain_asset.vector_sync_error,
    )


def domain_asset_to_api_schema(domain_asset: AssetMetadataDomain) -> AssetSchemaResponse:
    """Convert Domain AssetMetadata to API AssetSchemaResponse."""
    return AssetSchemaResponse(
        asset_name=domain_asset.asset_name,
        asset_type=domain_asset.asset_type,
        columns=[col.to_dict() for col in domain_asset.columns],
        row_count=domain_asset.row_count,
        data_source_id=domain_asset.data_source_id,
    )
