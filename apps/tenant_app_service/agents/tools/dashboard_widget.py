"""Widget-related dashboard tools: add, update, and remove widgets."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.dashboard.adapters import (
    chart_display_config_dto_to_domain,
    domain_filter_to_dto,
    domain_widget_to_dto,
    field_mapping_dto_to_domain,
    widget_position_dto_to_domain,
)
from apps.shared.dashboard.domain import ChartType
from apps.shared.dashboard.schemas import (
    ChartDisplayConfigDTO,
    DashboardWidgetToolAddRequest,
    DashboardWidgetToolCreatePayload,
    DashboardWidgetToolUpdateRequest,
    DashboardWidgetToolValidateRequest,
    FieldMappingDTO,
    WidgetPositionDTO,
)
from apps.shared.dashboard.service import DashboardService
from apps.shared.data_source import AssetMetadataRepository, DataSourceRepository, DataSourceService
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


def _actor_ctx(runtime) -> ActorContext:
    return ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )


@tool(args_schema=DashboardWidgetToolValidateRequest)
async def validate_widget_query(
    dashboard_id: int,
    data_source_id: int,
    query: str,
    config: RunnableConfig = None,
) -> ToolResult:
    """Validate widget SQL by running dashboard-scoped preview with limit=1."""
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with app_db_session() as session:
        dashboard_service = DashboardService.create(tenant_id=tenant_id, db_session=session)

        try:
            data_source_service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=DataSourceRepository(session),
                asset_repo=AssetMetadataRepository(session),
            )
            preview = await dashboard_service.preview_dashboard_sql_for_actor(
                dashboard_id=dashboard_id,
                data_source_id=data_source_id,
                query=query,
                actor=_actor_ctx(runtime),
                data_source_service=data_source_service,
                limit=1,
            )

            return ToolResult.success(
                {
                    "valid": True,
                    "message": "Query preview execution succeeded",
                    "columns": preview["columns"],
                    "rows": preview["rows"],
                }
            )
        except ValidationError as exc:
            dashboard = await dashboard_service.get_dashboard_for_actor(
                dashboard_id=dashboard_id,
                actor=_actor_ctx(runtime),
            )
            filter_dtos = [domain_filter_to_dto(f) for f in (dashboard.config.filters or [])]
            return ToolResult.error_result(
                code="WIDGET_VALIDATION_FAILED",
                message=str(exc),
                metadata={
                    "filters": [f.model_dump(by_alias=True) for f in filter_dtos],
                    "context": None,
                },
            )
        except Exception as exc:
            return ToolResult.error_result(
                code="WIDGET_VALIDATION_FAILED",
                message=str(exc),
                metadata={"filters": [], "context": None},
            )


@tool(args_schema=DashboardWidgetToolAddRequest)
async def add_widget_to_dashboard(
    dashboard_id: int,
    widget_data: DashboardWidgetToolCreatePayload,
    config: RunnableConfig = None,
) -> ToolResult:
    """Add widget to dashboard with SQL query and field mapping.

    Field mapping must match query column names. Common patterns:
    - METRIC: {"value": "col"}
    - LINE/BAR/AREA/GROUPED_BAR/STACKED_BAR/MULTI_LINE/MULTI_AREA: {"xAxis": "col1", "series": ["col2", ...]}
    - PIE: {"xAxis": "labelCol", "value": "valueCol"}
    - SCATTER: {"xAxis": "x", "yAxis": "y", "size": "s", "color": "c"}
    - HEATMAP: {"xAxis": "col_x", "yAxis": "col_y", "value": "col_value"}
    - GAUGE: {"value": "col"}
    - TABLE: null (auto-detects columns)

    Args:
        dashboard_id: Target dashboard ID
        widget_data: Widget payload containing all configuration parameters
        config: Runtime config

    Returns:
        JSON with dashboard_id, widget_id, position, preview_url
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with app_db_session() as session:
        service = DashboardService.create(tenant_id=tenant_id, db_session=session)
        try:
            new_widget = await service.add_widget_for_actor(
                dashboard_id=dashboard_id,
                actor=_actor_ctx(runtime),
                widget_type=widget_data.widget_type,
                chart_type=widget_data.chart_type,
                position=widget_position_dto_to_domain(widget_data.position)
                if widget_data.position is not None
                else None,
                data_source_id=widget_data.data_source_id,
                query=widget_data.query,
                field_mapping=field_mapping_dto_to_domain(widget_data.field_mapping),
                display_config=chart_display_config_dto_to_domain(widget_data.display_config),
            )
            return ToolResult.success(domain_widget_to_dto(new_widget).model_dump(exclude_none=True))
        except ResourceNotFoundError as e:
            return ToolResult.error_result(code="DASHBOARD_NOT_FOUND", message=str(e))
        except ValidationError as e:
            return ToolResult.error_result(code="WIDGET_VALIDATION_FAILED", message=str(e))


@tool(args_schema=DashboardWidgetToolUpdateRequest)
async def update_widget(
    dashboard_id: int,
    widget_id: str,
    chart_type: ChartType | None = None,
    position: WidgetPositionDTO | None = None,
    data_source_id: int | None = None,
    query: str | None = None,
    field_mapping: FieldMappingDTO | None = None,
    display_config: ChartDisplayConfigDTO | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Update existing widget properties.

    Args:
        dashboard_id: Target dashboard ID
        widget_id: Widget ID in the dashboard
        chart_type: New chart type
        position: New grid position (x,y,w,h)
        data_source_id: New data source ID
        query: New SQL query
        field_mapping: New field mapping (structured object)
        display_config: Updated display config (replaces existing, structured object)

    Returns:
        JSON with dashboard_id, widget_id, position, preview_url
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with app_db_session() as session:
        service = DashboardService.create(tenant_id=tenant_id, db_session=session)
        try:
            updated_widget = await service.update_widget_for_actor(
                dashboard_id=dashboard_id,
                widget_id=widget_id,
                actor=_actor_ctx(runtime),
                chart_type=chart_type,
                position=widget_position_dto_to_domain(position) if position is not None else None,
                data_source_id=data_source_id,
                query=query,
                field_mapping=field_mapping_dto_to_domain(field_mapping) if field_mapping is not None else None,
                display_config=chart_display_config_dto_to_domain(display_config)
                if display_config is not None
                else None,
            )
            return ToolResult.success(domain_widget_to_dto(updated_widget).model_dump(exclude_none=True))
        except ResourceNotFoundError as e:
            return ToolResult.error_result(code="DASHBOARD_WIDGET_NOT_FOUND", message=str(e))
        except ValidationError as e:
            return ToolResult.error_result(code="WIDGET_VALIDATION_FAILED", message=str(e))


@tool
async def remove_widget(
    dashboard_id: int,
    widget_id: str,
    config: RunnableConfig = None,
) -> ToolResult:
    """Remove widget from dashboard.

    Args:
        dashboard_id: Dashboard ID
        widget_id: Widget ID in the dashboard
        config: Runtime config

    Returns:
        JSON with updated dashboard configuration
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with app_db_session() as session:
        service = DashboardService.create(tenant_id=tenant_id, db_session=session)
        try:
            await service.remove_widget_for_actor(
                dashboard_id=dashboard_id,
                widget_id=widget_id,
                actor=_actor_ctx(runtime),
            )
            return ToolResult.success({"id": widget_id, "deleted": True})
        except ResourceNotFoundError as e:
            return ToolResult.error_result(code="DASHBOARD_WIDGET_NOT_FOUND", message=str(e))
