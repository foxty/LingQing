"""Dashboard base tools: creation, configuration, and layout management."""

from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.dashboard.adapters import dashboard_config_to_dict
from apps.shared.dashboard.domain import DEFAULT_DASHBOARD_LAYOUT, DashboardConfig
from apps.shared.dashboard.service import DashboardService
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_rbac import tool_rbac_denied
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


def _actor_ctx(runtime) -> ActorContext:
    return ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )


@tool
async def create_dashboard(
    title: str,
    description: str,
    config: RunnableConfig,
) -> ToolResult:
    """Create empty dashboard with 12-column grid. Widgets added separately.

    Args:
        title: Dashboard title
        description: Dashboard description
        config: Runtime config

    Returns:
        JSON with dashboard_id, dashboard_name, preview_url, artifact details, message
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    user_id = runtime.user.user_id
    thread_id = runtime.thread_id  # Get current thread_id

    logger.info(
        "Creating empty dashboard",
        extra={"title": title, "description": description, "thread_id": thread_id},
    )

    async with app_db_session() as session:
        denied = await tool_rbac_denied(
            session,
            tenant_id,
            runtime.user.role,
            TenantAppPermissions.DASHBOARDS_WRITE,
            denied_message="You do not have permission to create dashboards",
        )
        if denied:
            return denied

        dashboard_service = DashboardService.create(tenant_id=tenant_id, db_session=session)

        # Create empty dashboard with default layout
        dashboard_config = DashboardConfig(
            layout=DEFAULT_DASHBOARD_LAYOUT,
            widgets=[],
        )

        config_dict = dashboard_config_to_dict(dashboard_config)

        # Auto-append timestamp to dashboard name
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        dashboard_name = f"{title}_{timestamp}"

        result = await dashboard_service.create_dashboard(
            name=dashboard_name,
            description=description,
            config=config_dict,
            owner_id=user_id,
            thread_id=thread_id,
        )

        dashboard = result.dashboard
        if result.artifact:
            logger.info(f"Linked dashboard {dashboard.id} to thread {thread_id}")

        await session.commit()

        return ToolResult.success(
            {
                "dashboard_id": dashboard.id,
                "dashboard_name": dashboard.name,
                "preview_url": f"/dashboards/{dashboard.id}/embed",
                "message": f"Dashboard '{dashboard.name}' created successfully (empty, ready to add widgets)",
                "artifact": result.artifact.model_dump() if result.artifact else None,
            }
        )


@tool
async def get_dashboard_config(
    dashboard_id: int,
    config: RunnableConfig = None,
) -> ToolResult:
    """Get dashboard configuration with layout, widgets (with _order), and filters.

    Args:
        dashboard_id: Dashboard ID
        config: Runtime config

    Returns:
        JSON with dashboard_id, name, description, config (layout/widgets/filters), message
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with app_db_session() as session:
        dashboard_service = DashboardService.create(tenant_id=tenant_id, db_session=session)
        dashboard = await dashboard_service.get_dashboard_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(runtime),
        )

        if not dashboard:
            return ToolResult.error_result(
                code="DASHBOARD_NOT_FOUND",
                message=f"Dashboard {dashboard_id} not found",
            )

        # Enhance widgets with order information for natural language reference
        dashboard_config = dashboard.config

        # Build response with typed config
        config_dict = dashboard_config_to_dict(dashboard_config)
        widgets = config_dict.get("widgets", [])
        for idx, widget in enumerate(widgets, start=1):
            widget["_order"] = idx  # Add 1-based order for reference

        return ToolResult.success(
            {
                "dashboard_id": dashboard.id,
                "name": dashboard.name,
                "description": dashboard.description,
                "config": config_dict,
                "message": f"Dashboard '{dashboard.name}' has {len(dashboard.config.widgets)} widgets",
            }
        )


@tool
async def update_dashboard_layout(
    dashboard_id: int,
    cols: int | None = None,
    rows: int | None = None,
    gap: int | None = None,
    row_height: int | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Update dashboard layout settings. All parameters optional.

    Args:
        dashboard_id: Dashboard ID
        cols: Grid columns
        rows: Grid rows
        gap: Widget gap (pixels)
        row_height: Row height (pixels)
        config: Runtime config

    Returns:
        JSON with dashboard_id and updated layout
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id

    async with app_db_session() as session:
        dashboard_service = DashboardService.create(tenant_id=tenant_id, db_session=session)
        dashboard = await dashboard_service.get_dashboard_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(runtime),
        )

        if not dashboard:
            return ToolResult.error_result(
                code="DASHBOARD_NOT_FOUND",
                message=f"Dashboard {dashboard_id} not found",
            )

        dashboard_config = dashboard.config

        # Update layout properties
        if cols is not None:
            dashboard_config.layout.cols = cols
        if rows is not None:
            dashboard_config.layout.rows = rows
        if gap is not None:
            dashboard_config.layout.gap = gap
        if row_height is not None:
            dashboard_config.layout.row_height = row_height

        # Save changes
        await dashboard_service.update_dashboard_for_actor(
            dashboard_id=dashboard_id,
            actor=_actor_ctx(runtime),
            config=dashboard_config,
        )

        layout_dict = {
            "cols": dashboard_config.layout.cols,
            "rows": dashboard_config.layout.rows,
            "gap": dashboard_config.layout.gap,
            "rowHeight": dashboard_config.layout.row_height,
        }

        return ToolResult.success(
            {
                "dashboard_id": dashboard.id,
                "layout": layout_dict,
            }
        )
