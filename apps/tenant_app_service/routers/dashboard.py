"""Dashboard API routes."""

from dataclasses import replace
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import get_current_user, require_permission, require_permission_released
from apps.shared.core.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.dashboard.adapters import (
    chart_display_config_dto_to_domain,
    dashboard_config_dto_to_domain,
    dashboard_filter_option_dto_to_domain,
    domain_dashboard_to_response,
    domain_filter_to_dto,
    domain_widget_to_dto,
    field_mapping_dto_to_domain,
    widget_position_dto_to_domain,
)
from apps.shared.dashboard.domain import DashboardLayout
from apps.shared.dashboard.schemas import (
    DashboardCreate,
    DashboardFilterCreateRequest,
    DashboardFilterDTO,
    DashboardFilterOptionResponse,
    DashboardFilterOptionsResponse,
    DashboardFilterUpdateDTO,
    DashboardListItemResponse,
    DashboardQueryPreviewRequest,
    DashboardQueryPreviewResponse,
    DashboardResponse,
    DashboardSqlPreviewRequest,
    DashboardUpdate,
    DashboardWidgetCreateRequest,
    DashboardWidgetDTO,
    DashboardWidgetQueryDataRequest,
    DashboardWidgetUpdateRequest,
)
from apps.shared.dashboard.service import DashboardService, apply_filter_value_overrides
from apps.shared.data_source import AssetMetadataRepository, DataSourceRepository, DataSourceService
from apps.shared.db.session import app_db_session, get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _create_dashboard_service(db: AsyncSession, tenant_id: int) -> DashboardService:
    return DashboardService.create(tenant_id=tenant_id, db_session=db)


def _extract_agent_thread_id(request: Request) -> str | None:
    """Extract agent thread id from custom headers.

    Supports both direct header and serialized context header forms.
    """
    thread_id = request.headers.get("x-agent-thread-id")
    if thread_id:
        return thread_id


def _actor_ctx(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.post(
    "",
    response_model=DashboardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Dashboard",
)
async def create_dashboard(
    request: Request,
    payload: DashboardCreate = Body(..., description="Dashboard create payload"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        dashboard_name = f"{payload.name}_{timestamp}"
        resolved_thread_id = payload.thread_id or _extract_agent_thread_id(request)
        service = _create_dashboard_service(db, current_user.tenant_id)
        result = await service.create_dashboard(
            name=dashboard_name,
            description=payload.description,
            config=dashboard_config_dto_to_domain(payload.config),
            owner_id=current_user.id,
            thread_id=resolved_thread_id,
        )

        dashboard_response = domain_dashboard_to_response(result.dashboard)
        return dashboard_response.model_copy(update={"artifact": result.artifact})
    except DuplicateResourceError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("", response_model=list[DashboardListItemResponse], summary="List Dashboards")
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(get_current_user),
):
    service = _create_dashboard_service(db, current_user.tenant_id)
    dashboards = await service.list_dashboards_for_actor(actor=_actor_ctx(current_user))
    return [
        DashboardListItemResponse(
            id=dashboard.id,
            tenant_id=dashboard.tenant_id,
            name=dashboard.name,
            description=dashboard.description,
            owner_id=dashboard.owner_id,
            owner_username=dashboard.owner_username,
            created_at=dashboard.created_at,
            updated_at=dashboard.updated_at,
        )
        for dashboard in dashboards
    ]


@router.get("/{dashboard_id}", response_model=DashboardResponse, summary="Get Dashboard by ID")
async def get_dashboard(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(get_current_user),
):
    service = _create_dashboard_service(db, current_user.tenant_id)
    dashboard = await service.get_dashboard_for_actor(
        dashboard_id,
        actor=_actor_ctx(current_user),
    )
    return domain_dashboard_to_response(dashboard)


@router.put("/{dashboard_id}", response_model=DashboardResponse, summary="Update Dashboard by ID")
async def update_dashboard(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    payload: DashboardUpdate = Body(..., description="Dashboard update payload"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        existing_dashboard = await service.get_dashboard_for_actor(
            dashboard_id,
            actor=_actor_ctx(current_user),
        )

        updated_config = None
        if payload.layout is not None:
            updated_config = replace(
                existing_dashboard.config,
                layout=DashboardLayout(
                    type=payload.layout.type,
                    cols=payload.layout.cols,
                    rows=payload.layout.rows,
                    gap=payload.layout.gap,
                    row_height=payload.layout.row_height,
                ),
            )

        dashboard = await service.update_dashboard_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(current_user),
            name=payload.name,
            description=payload.description,
            config=updated_config,
        )
        return domain_dashboard_to_response(dashboard)
    except DuplicateResourceError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Dashboard")
async def delete_dashboard(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        await service.delete_dashboard_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(current_user),
        )
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{dashboard_id}/widgets/{widget_id}/query-data", summary="Query Widget Data by Widget ID")
async def query_dashboard_widget_data(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    widget_id: str = Path(..., description="Widget ID to query data for"),
    payload: DashboardWidgetQueryDataRequest | None = Body(default=None),
    # Do not use Depends(get_db) or Depends(require_permission()) here.
    # FastAPI keeps a yielded get_db session open until the response is sent.
    # require_permission() / get_current_user() both Depends(get_db), so they
    # would pin a pool connection across the warehouse wait below.
    # require_permission_released() authenticates in a short app_db_session
    # and closes it before this handler runs.
    current_user: UserDTO = Depends(require_permission_released(Permissions.DASHBOARDS_SQL_EXECUTE)),
):
    actor = _actor_ctx(current_user)
    # Do not use Depends(get_db) here. FastAPI keeps injected sessions open until
    # the response is sent, and this handler waits on a warehouse query. A short
    # app_db_session covers ACL/compile only; the pool connection is released
    # before execute_dataframe().
    async with app_db_session() as db:
        service = _create_dashboard_service(db, current_user.tenant_id)
        dashboard = await service.get_dashboard_for_actor(
            dashboard_id=dashboard_id,
            actor=actor,
        )

        widget = dashboard.get_widget_by_id(widget_id)
        if not widget:
            raise ResourceNotFoundError(f"Widget '{widget_id}' not found in dashboard {dashboard_id}")

        data_source_service = DataSourceService(
            tenant_id=current_user.tenant_id,
            data_source_repo=DataSourceRepository(db),
            asset_repo=AssetMetadataRepository(db),
        )
        filters = apply_filter_value_overrides(
            dashboard.config.filters,
            payload.filters if payload else None,
        )
        prepared = await service.prepare_widget_analytics_query(
            widget,
            data_source_service=data_source_service,
            user_id=current_user.id,
            user_role=current_user.role,
            filters=filters,
        )

    df = await prepared.execute_dataframe()
    return {"data": DashboardService.materialize_widget_rows(df)}


@router.post(
    "/{dashboard_id}/widgets/query-preview",
    response_model=DashboardQueryPreviewResponse,
    summary="Preview SQL with Dashboard Filter Macros",
)
async def query_dashboard_sql_preview(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    payload: DashboardSqlPreviewRequest = Body(..., description="SQL preview request"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_SQL_EXECUTE)),
):
    service = _create_dashboard_service(db, current_user.tenant_id)
    data_source_service = DataSourceService(
        tenant_id=current_user.tenant_id,
        data_source_repo=DataSourceRepository(db),
        asset_repo=AssetMetadataRepository(db),
    )
    return await service.preview_dashboard_sql_for_actor(
        dashboard_id=dashboard_id,
        data_source_id=payload.data_source_id,
        query=payload.query,
        actor=_actor_ctx(current_user),
        data_source_service=data_source_service,
        limit=payload.limit,
    )


@router.post(
    "/{dashboard_id}/widgets/{widget_id}/query-preview",
    response_model=DashboardQueryPreviewResponse,
    summary="Preview Widget Query by Widget ID",
)
async def query_dashboard_widget_preview(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    widget_id: str = Path(..., description="Widget ID to preview data for"),
    payload: DashboardQueryPreviewRequest = Body(..., description="Widget query preview request payload"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_SQL_EXECUTE)),
):
    service = _create_dashboard_service(db, current_user.tenant_id)
    data_source_service = DataSourceService(
        tenant_id=current_user.tenant_id,
        data_source_repo=DataSourceRepository(db),
        asset_repo=AssetMetadataRepository(db),
    )
    return await service.preview_dashboard_widget_sql_for_actor(
        dashboard_id=dashboard_id,
        widget_id=widget_id,
        actor=_actor_ctx(current_user),
        data_source_service=data_source_service,
        limit=payload.limit,
        query=payload.query,
        data_source_id=payload.data_source_id,
    )


@router.get(
    "/{dashboard_id}/filters/{filter_id}/options",
    response_model=DashboardFilterOptionsResponse,
    summary="Get Filter Options",
)
async def get_dashboard_filter_options(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    filter_id: str = Path(..., description="Filter ID in the dashboard"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_SQL_EXECUTE)),
):
    service = _create_dashboard_service(db, current_user.tenant_id)
    data_source_service = DataSourceService(
        tenant_id=current_user.tenant_id,
        data_source_repo=DataSourceRepository(db),
        asset_repo=AssetMetadataRepository(db),
    )
    try:
        result = await service.get_filter_options_for_actor(
            dashboard_id=dashboard_id,
            filter_id=filter_id,
            actor=_actor_ctx(current_user),
            data_source_service=data_source_service,
        )
        return DashboardFilterOptionsResponse(
            options=[
                DashboardFilterOptionResponse(label=option.label, value=option.value) for option in result.options
            ],
            has_error=result.has_error,
            error_message=result.error_message,
        )
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/{dashboard_id}/widgets",
    response_model=DashboardWidgetDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Add Dashboard Widget",
)
async def add_dashboard_widget(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    payload: DashboardWidgetCreateRequest = Body(..., description="Dashboard widget create payload"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        new_widget = await service.add_widget_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(current_user),
            widget_type=payload.type,
            chart_type=payload.chart_type,
            position=widget_position_dto_to_domain(payload.position),
            data_source_id=payload.data_source_id,
            query=payload.query,
            field_mapping=field_mapping_dto_to_domain(payload.field_mapping),
            display_config=chart_display_config_dto_to_domain(payload.display_config),
        )
        return domain_widget_to_dto(new_widget)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=DashboardWidgetDTO, summary="Update Widget")
async def update_dashboard_widget(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    payload: DashboardWidgetUpdateRequest = Body(..., description="Dashboard widget update payload"),
    widget_id: str = Path(..., description="Widget ID in the dashboard"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        updated_widget = await service.update_widget_for_actor(
            dashboard_id=dashboard_id,
            widget_id=widget_id,
            actor=_actor_ctx(current_user),
            chart_type=payload.chart_type,
            position=widget_position_dto_to_domain(payload.position) if payload.position is not None else None,
            data_source_id=payload.data_source_id,
            query=payload.query,
            field_mapping=field_mapping_dto_to_domain(payload.field_mapping)
            if payload.field_mapping is not None
            else None,
            display_config=chart_display_config_dto_to_domain(payload.display_config)
            if payload.display_config is not None
            else None,
        )
        return domain_widget_to_dto(updated_widget)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{dashboard_id}/widgets/{widget_id}", response_model=DashboardResponse, summary="Remove Widget")
async def remove_dashboard_widget(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    widget_id: str = Path(..., description="Widget ID in the dashboard"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        updated = await service.remove_widget_for_actor(
            dashboard_id=dashboard_id,
            widget_id=widget_id,
            actor=_actor_ctx(current_user),
        )
        return domain_dashboard_to_response(updated)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/{dashboard_id}/filters",
    response_model=DashboardFilterDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Add Dashboard Filter",
)
async def add_dashboard_filter(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    payload: DashboardFilterCreateRequest = Body(..., description="Dashboard filter create payload"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    """Add filter to dashboard. Types: time_range (SQL: $time_filter(:param_key, field)), dropdown_static/dropdown_datasource (SQL: $in_or_equal(:param_key, field))."""
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        new_filter = await service.add_filter_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(current_user),
            name=payload.name,
            filter_type=payload.type,
            param_key=payload.param_key,
            value=payload.value,
            data_source_id=payload.data_source_id,
            options_query=payload.options_query,
            options=[dashboard_filter_option_dto_to_domain(o) for o in payload.options] if payload.options else None,
            allow_multiple=payload.allow_multiple,
            time_precision=payload.time_precision,
            description=payload.description,
            required=payload.required or False,
            validate_options_query=True,
            data_source_service=DataSourceService(
                tenant_id=current_user.tenant_id,
                data_source_repo=DataSourceRepository(db),
                asset_repo=AssetMetadataRepository(db),
            ),
        )
        return domain_filter_to_dto(new_filter)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/{dashboard_id}/filters/{filter_id}", response_model=DashboardFilterDTO, summary="Update Filter")
async def update_dashboard_filter(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    filter_id: str = Path(..., description="Filter ID in the dashboard"),
    payload: DashboardFilterUpdateDTO = Body(..., description="Dashboard filter update payload"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        update_data = payload.model_dump(exclude_unset=True)
        # Convert options DTO list to domain objects before passing to service.
        if "options" in update_data and update_data["options"] is not None:
            update_data["options"] = [dashboard_filter_option_dto_to_domain(o) for o in payload.options or []]
        updated_filter = await service.update_filter_for_actor(
            dashboard_id=dashboard_id,
            filter_id=filter_id,
            actor=_actor_ctx(current_user),
            field_updates=update_data,
            validate_options_query=True,
            data_source_service=DataSourceService(
                tenant_id=current_user.tenant_id,
                data_source_repo=DataSourceRepository(db),
                asset_repo=AssetMetadataRepository(db),
            ),
        )
        return domain_filter_to_dto(updated_filter)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{dashboard_id}/filters/{filter_id}", response_model=DashboardResponse, summary="Remove Filter")
async def remove_dashboard_filter(
    dashboard_id: int = Path(..., description="Dashboard ID"),
    filter_id: str = Path(..., description="Filter ID in the dashboard"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_WRITE)),
):
    try:
        service = _create_dashboard_service(db, current_user.tenant_id)
        updated = await service.remove_filter_for_actor(
            dashboard_id=dashboard_id,
            filter_id=filter_id,
            actor=_actor_ctx(current_user),
        )
        return domain_dashboard_to_response(updated)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
