"""Data source and asset management API routes."""

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.data_source import (
    AssetMetadataRepository,
    DataSourceRepository,
    DataSourceService,
)
from apps.shared.data_source.adapters import domain_asset_to_api_schema, domain_data_source_to_api
from apps.shared.data_source.asset_metadata_service import AssetMetadataService
from apps.shared.data_source.schemas import (
    AssetMetadataOverrideUpdate,
    AssetMetadataResponse,
    AssetSchemaResponse,
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceQueryRequest,
    DataSourceResponse,
    DataSourceUpdate,
    DiscoverAssetsResponse,
    TestConnectionResponse,
)
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.domain.value_objects import DataSourceTypeStr
from apps.shared.schemas.pagination import PaginatedResponse
from apps.shared.schemas.user import UserDTO
from apps.shared.tag.adapters import domain_tag_value_to_api
from apps.shared.tag.schemas import TagBindingCreateRequest, TagValueDTO
from apps.shared.tag.service import TagService
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


def _create_data_source_service(db: AsyncSession, tenant_id: int) -> DataSourceService:
    """Create DataSourceService with injected repositories.

    Args:
        db: Database session
        tenant_id: Tenant ID

    Returns:
        Configured DataSourceService instance
    """
    return DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(db),
        asset_repo=AssetMetadataRepository(db),
    )


def _create_asset_metadata_service(db: AsyncSession, tenant_id: int) -> AssetMetadataService:
    """Create AssetMetadataService with injected repositories.

    Args:
        db: Database session
        tenant_id: Tenant ID

    Returns:
        Configured AssetMetadataService instance
    """
    return AssetMetadataService(tenant_id=tenant_id, db_session=db)


def _create_tag_service(db: AsyncSession, tenant_id: int) -> TagService:
    return TagService.create(tenant_id, db)


def _actor_from_user(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


# ============ Connection Testing ============


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    type: DataSourceTypeStr = Form(..., description="Database type"),
    config: str = Form(..., description="Connection configuration as JSON string"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Test database connection for PostgreSQL/MySQL only.

    Args:
        type: Database type
        config: Connection configuration as JSON string
        current_user: Current authenticated user

    Returns:
        Connection test result
    """
    import json

    try:
        # Parse config
        config_dict = json.loads(config)
        service = _create_data_source_service(db, current_user.tenant_id)
        return await service.test_connection(type, config_dict)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid config JSON",
        )
    except Exception as e:
        logger.error(f"Connection test failed: {e}", exc_info=True)
        return TestConnectionResponse(
            success=False,
            message="Connection test failed",
            error=str(e),
        )


@router.get("/{data_source_id}/discover-assets", response_model=DiscoverAssetsResponse, include_in_schema=False)
async def discover_assets(
    data_source_id: int,
    query: str | None = Query(None, min_length=1, description="Search query"),
    light: bool = Query(False, description="Use lightweight discovery (no schema metadata)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Discover available assets from a saved data source.

    Args:
        data_source_id: Data source ID
        current_user: Current authenticated user

    Returns:
        List of discovered assets
    """
    try:
        service = _create_data_source_service(db, current_user.tenant_id)
        actor = _actor_from_user(current_user)

        assets, total, requires_query = await service.discover_assets_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            query=query,
            include_schema=not light,
        )

        return DiscoverAssetsResponse(
            assets=assets,
            total=total,
            requires_query=requires_query,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Asset discovery failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Asset discovery failed: {str(e)}",
        )


# ============ Data Source CRUD ============


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_data_source(
    name: str = Form(..., description="Data source name"),
    type: DataSourceTypeStr = Form(..., description="Database type"),
    config: str = Form(..., description="Connection configuration as JSON string"),
    description: str | None = Form(None, description="Data source description"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Create a new data source (without assets, assets will be selected later).

    Args:
        name: Data source name
        type: Database type
        config: Connection configuration as JSON string
        description: Optional description
        current_user: Current authenticated user

    Returns:
        Created data source

    Raises:
        HTTPException: If data source name already exists
    """
    import json

    try:
        # Parse config
        config_dict = json.loads(config)

        # Create data source (without assets)
        service = _create_data_source_service(db, current_user.tenant_id)
        data_source_create = DataSourceCreate(
            name=name,
            type=type,
            managed=False,
            config=config_dict,
            description=description,
        )
        data_source = await service.create_data_source(data_source_create, owner_id=current_user.id)

        return DataSourceResponse.model_validate(data_source)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in config",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create data source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create data source: {str(e)}",
        )


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    query: str | None = Query(None, min_length=1, description="Search query"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_READ)),
):
    """List all data sources for the current tenant.

    Args:
        current_user: Current authenticated user

    Returns:
        List of data sources
    """
    try:
        service = _create_data_source_service(db, current_user.tenant_id)
        data_sources, pagination = await service.list_data_sources_paginated_for_actor(
            actor=_actor_from_user(current_user),
            page=page,
            page_size=page_size,
            query=query,
        )
        return DataSourceListResponse(
            items=[domain_data_source_to_api(ds) for ds in data_sources],
            total=pagination.total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=pagination.total_pages,
        )
    except Exception as e:
        logger.exception(f"Failed to list data sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list data sources",
        )


@router.get("/{data_source_id}", response_model=DataSourceResponse)
async def get_data_source(
    data_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_READ)),
):
    """Get a data source by ID.

    Args:
        data_source_id: Data source ID
        current_user: Current authenticated user

    Returns:
        Data source details

    Raises:
        HTTPException: If data source not found
    """
    service = _create_data_source_service(db, current_user.tenant_id)
    data_source = await service.get_data_source_for_actor(
        data_source_id=data_source_id,
        actor=_actor_from_user(current_user),
    )
    return DataSourceResponse.model_validate(data_source)


@router.put("/{data_source_id}", response_model=DataSourceResponse, include_in_schema=False)
async def update_data_source(
    data_source_id: int,
    name: str | None = Form(None, description="Data source name"),
    config: str | None = Form(None, description="Connection configuration as JSON string"),
    description: str | None = Form(None, description="Data source description"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Update a data source configuration.

    Args:
        data_source_id: Data source ID
        name: Optional new name
        config: Optional new config as JSON string
        description: Optional new description
        current_user: Current authenticated user

    Returns:
        Updated data source

    Raises:
        HTTPException: If data source not found
    """
    import json

    try:
        service = _create_data_source_service(db, current_user.tenant_id)
        actor = _actor_from_user(current_user)
        updated = await service.update_data_source_for_actor(
            data_source_id=data_source_id,
            update_data=DataSourceUpdate(
                name=name,
                config=json.loads(config) if config else None,
                description=description,
            ),
            actor=actor,
        )

        return DataSourceResponse.model_validate(updated)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in config",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update data source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update data source: {str(e)}",
        )


@router.delete("/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def delete_data_source(
    data_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Delete a data source and all its assets.

    Args:
        data_source_id: Data source ID
        current_user: Current authenticated user

    Raises:
        HTTPException: If data source not found or is managed
    """
    service = _create_data_source_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)
    await service.delete_data_source_for_actor(
        data_source_id=data_source_id,
        actor=actor,
    )


# ============ Asset Management ============


@router.put("/{data_source_id}/assets/selection", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def update_asset_selection(
    data_source_id: int,
    asset_names: list[str] = Query(..., description="Selected asset names"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Update selected assets for a data source.

    Args:
        data_source_id: Data source ID
        asset_names: List of asset names to select
        current_user: Current authenticated user

    Raises:
        HTTPException: If data source not found
    """
    try:
        ds_service = _create_data_source_service(db, current_user.tenant_id)
        asset_service = _create_asset_metadata_service(db, current_user.tenant_id)
        actor = _actor_from_user(current_user)

        # Discover only selected assets (schema fetch only for selected names)
        discovered = await ds_service.discover_assets_by_names_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            asset_names=asset_names,
        )

        discovered_names = {asset.name for asset in discovered}
        missing = [name for name in asset_names if name not in discovered_names]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assets not found in data source: {missing}",
            )

        # Sync asset selection using AssetMetadataService
        result = await asset_service.sync_assets_selection_for_actor(
            actor=actor,
            data_source_id=data_source_id,
            selected_asset_names=asset_names,
            discovered_assets=discovered,
        )
        logger.info(
            f"Asset selection synced for data_source_id={data_source_id}: "
            f"deleted={result['deleted']}, created={result['created']}, kept={result['kept']}"
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update asset selection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update asset selection: {str(e)}",
        )


@router.get("/{data_source_id}/assets", response_model=PaginatedResponse[AssetMetadataResponse])
async def list_assets(
    data_source_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    query: str | None = Query(None, min_length=1, description="Search query"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_READ)),
):
    """List assets for a data source with pagination.

    Args:
        data_source_id: Data source ID
        page: Page number (1-indexed). Defaults to 1.
        page_size: Items per page. Defaults to 10.
        current_user: Current authenticated user

    Returns:
        Paginated list of assets with sync status
    """
    asset_service = _create_asset_metadata_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)

    # Service returns DTOs via DB → Domain → DTO chain
    assets, pagination = await asset_service.list_assets_for_actor(
        actor=actor,
        data_source_id=data_source_id,
        page=page,
        page_size=page_size,
        query=query,
    )

    return PaginatedResponse(
        items=assets,
        total=pagination.total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages,
    )


@router.put(
    "/{data_source_id}/assets/{asset_id}/meta-override",
    response_model=AssetMetadataResponse,
    include_in_schema=False,
)
async def update_asset_meta_override(
    data_source_id: int,
    asset_id: int,
    payload: AssetMetadataOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Update user overrides for asset metadata."""
    from apps.shared.data_source.adapters import domain_asset_metadata_to_api

    actor = _actor_from_user(current_user)

    asset_service = _create_asset_metadata_service(db, current_user.tenant_id)
    asset = await asset_service.update_asset_meta_override_for_actor(
        actor=actor,
        data_source_id=data_source_id,
        asset_id=asset_id,
        description=payload.description,
        column_description=payload.column_description,
    )
    return domain_asset_metadata_to_api(asset)


@router.post(
    "/{data_source_id}/assets/upload-csv",
    response_model=AssetMetadataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_csv(
    data_source_id: int,
    file: UploadFile = File(..., description="CSV file to upload"),
    asset_name: str = Form(..., description="Name for the asset (table name)"),
    description: str | None = Form(None, description="Optional description"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Upload a CSV file and import it into the analytics database as a new asset.

    Args:
        data_source_id: Data source ID
        file: CSV file to upload
        asset_name: Name for the asset (table name)
        description: Optional description
        current_user: Current authenticated user

    Returns:
        Created asset metadata

    Raises:
        HTTPException: If data source not found, asset already exists, or upload/import fails
    """
    from apps.shared.data_source.adapters import domain_asset_metadata_to_api

    # Validate file type
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported",
        )

    ds_service = _create_data_source_service(db, current_user.tenant_id)
    asset_service = _create_asset_metadata_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)

    # Check if asset already exists (fast fail before expensive operations)
    existing_asset = await asset_service.get_asset_by_name_for_actor(
        actor=actor,
        data_source_id=data_source_id,
        asset_name=asset_name,
    )
    if existing_asset:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset '{asset_name}' already exists in this data source",
        )

    try:
        # Save uploaded file to temporary location
        with NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        try:
            # Get DB manager and import CSV using AssetMetadataService
            db_manager = await ds_service.get_db_manager(data_source_id)
            async with db_manager as db:
                asset, rows_imported = await asset_service.import_csv_as_asset_for_actor(
                    actor=actor,
                    data_source_id=data_source_id,
                    asset_name=asset_name,
                    file_name=file.filename,
                    csv_path=temp_path,
                    db_manager=db,  # Inject DB manager
                    description=description,
                )
            logger.info(
                f"Successfully imported {rows_imported} rows into asset '{asset_name}' for data source {data_source_id}"
            )
            return domain_asset_metadata_to_api(asset)
        finally:
            # Clean up temporary file
            temp_path.unlink(missing_ok=True)
    except Exception as e:
        logger.exception(f"Failed to upload CSV: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload CSV: {str(e)}",
        )


@router.get("/{data_source_id}/assets/{asset_name}", response_model=AssetSchemaResponse)
async def get_asset_schema(
    data_source_id: int,
    asset_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_READ)),
):
    """Get schema information for an asset.

    Args:
        data_source_id: Data source ID
        asset_name: Asset name (table/view name)
        current_user: Current authenticated user

    Returns:
        Asset schema information

    Raises:
        HTTPException: If asset not found
    """
    try:
        asset_service = _create_asset_metadata_service(db, current_user.tenant_id)
        actor = _actor_from_user(current_user)

        asset = await asset_service.get_asset_by_name_for_actor(
            data_source_id=data_source_id,
            asset_name=asset_name,
            actor=actor,
        )

        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset '{asset_name}' not found",
            )

        return domain_asset_to_api_schema(asset)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get asset schema: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get asset schema",
        )


@router.post("/{data_source_id}/query")
async def query_data_source(
    data_source_id: int,
    query_request: DataSourceQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_READ)),
):
    """Execute read-only SQL on a data source.

    This endpoint is intended for agent/runtime SQL execution and is not limited
    to a pre-selected asset name.
    """
    try:
        service = _create_data_source_service(db, current_user.tenant_id)
        actor = _actor_from_user(current_user)

        df = await service.query_data_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            sql_query=query_request.sql,
            max_rows=query_request.limit,
        )

        return {
            "data_source_id": data_source_id,
            "row_count": len(df),
            "columns": df.columns.tolist(),
            "rows": df.to_dict(orient="records"),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to query data source {data_source_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}",
        )


@router.delete("/{data_source_id}/assets", include_in_schema=False)
async def delete_assets(
    data_source_id: int,
    asset_names: list[str] = Query(..., description="Names of assets to delete"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
):
    """Delete multiple data assets via query parameters."""
    ds_service = _create_data_source_service(db, current_user.tenant_id)
    asset_service = _create_asset_metadata_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)
    data_source = await ds_service.get_data_source_for_actor(
        data_source_id=data_source_id,
        actor=actor,
    )

    if not asset_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one asset name must be provided",
        )

    try:
        # For managed data sources, create callback to drop tables
        drop_table_callback = None
        if data_source.managed:

            async def drop_table(asset_name: str):
                await ds_service.drop_managed_table_for_actor(
                    data_source_id=data_source_id,
                    asset_name=asset_name,
                    actor=actor,
                )

            drop_table_callback = drop_table

        # Delete assets using AssetMetadataService
        deleted_count, failed_assets, errors = await asset_service.delete_assets_for_actor(
            actor=actor,
            data_source_id=data_source_id,
            asset_names=asset_names,
            drop_table_callback=drop_table_callback,
        )

        # Return result regardless of success/failure count
        # This allows clients to see which assets failed and why
        if deleted_count == 0 and len(failed_assets) == len(asset_names):
            # All assets failed to delete (e.g., not found)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No assets could be deleted. Errors: {errors}",
            )

        return {
            "deleted_count": deleted_count,
            "failed_assets": failed_assets,
            "errors": errors,
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{data_source_id}/tags", response_model=list[TagValueDTO])
async def list_data_source_tags(
    data_source_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_READ)),
    db: AsyncSession = Depends(get_db),
):
    ds_service = _create_data_source_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)
    await ds_service.require_read_access_for_actor(
        data_source_id=data_source_id,
        actor=actor,
    )

    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_values = await tag_service.list_tags_for_resource(RESOURCE_TYPE_DATA_SOURCE, data_source_id)
    return [domain_tag_value_to_api(tag_value) for tag_value in tag_values]


@router.post("/{data_source_id}/tags", response_model=TagValueDTO)
async def bind_data_source_tag(
    data_source_id: int,
    payload: TagBindingCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    ds_service = _create_data_source_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)
    await ds_service.require_write_access_for_actor(
        data_source_id=data_source_id,
        actor=actor,
    )

    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await tag_service.bind_tag_value(
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=data_source_id,
        tag_value_id=payload.tag_value_id,
        created_by=current_user.id,
    )
    return domain_tag_value_to_api(tag_value)


@router.delete("/{data_source_id}/tags/{tag_value_id}", status_code=204)
async def unbind_data_source_tag(
    data_source_id: int,
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    ds_service = _create_data_source_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)
    await ds_service.require_write_access_for_actor(
        data_source_id=data_source_id,
        actor=actor,
    )

    tag_service = _create_tag_service(db, current_user.tenant_id)
    await tag_service.unbind_tag_value(
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=data_source_id,
        tag_value_id=tag_value_id,
    )


# ========== Asset Metadata Sync Endpoints ==========


@router.post("/{data_source_id}/assets/{asset_id}/sync", response_model=dict, include_in_schema=False)
async def sync_asset_metadata(
    data_source_id: int,
    asset_id: int,
    force: bool = Query(False, description="Force full refresh"),
    current_user: UserDTO = Depends(require_permission(Permissions.DATA_SOURCES_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger asset metadata sync.

    Refreshes asset metadata (schema, row_count) from external data source.

    Args:
        data_source_id: Data source ID
        asset_id: Asset ID to sync
        force: Force full refresh regardless of timestamp
        current_user: Current user (permission required)
        db: Database session

    Returns:
        Sync result with status and statistics
    """
    logger.info(
        f"Manual asset sync requested: tenant={current_user.tenant_id}, "
        f"asset_id={asset_id}, force={force}, user={current_user.username}"
    )

    data_source_service = _create_data_source_service(db, current_user.tenant_id)
    actor = _actor_from_user(current_user)
    await data_source_service.require_write_access_for_actor(
        data_source_id=data_source_id,
        actor=actor,
    )

    # Create services with dependency injection
    asset_service = _create_asset_metadata_service(db, current_user.tenant_id)

    # Get db_manager for the asset's data source (injected dependency)
    db_manager = await data_source_service.get_db_manager(data_source_id)

    result = await asset_service.sync_asset_metadata(
        asset_id=asset_id,
        db_manager=db_manager,
        force=force,
    )

    return result
