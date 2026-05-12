"""Dashboard service for business logic."""

import uuid
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select

from apps.shared.artifact.access import ArtifactAccessGuard
from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.lifecycle import ArtifactLifecycle
from apps.shared.artifact.schemas import Artifact
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    SQLPreviewError,
    ValidationError,
)
from apps.shared.core.transaction import transaction
from apps.shared.dashboard.adapters import dashboard_config_to_dict
from apps.shared.dashboard.domain import (
    ChartDisplayConfig,
    DashboardConfig,
    DashboardDomain,
    DashboardFilter,
    DashboardFilterOption,
    DashboardFilterOptionsResult,
    DashboardWidget,
    FieldMapping,
    WidgetPosition,
)
from apps.shared.dashboard.query_compiler import compile_query
from apps.shared.dashboard.repository import DashboardRepository
from apps.shared.dashboard.schemas import (
    DashboardCreateWithArtifactResult,
    DashboardFilterValueOverrideDTO,
)
from apps.shared.dashboard.types import ChartType, FilterType, TimePrecision, WidgetType
from apps.shared.data_source import DataSourceService
from apps.shared.db.models import ChatThread
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.value_objects import SQLDialectStr, resolve_sql_dialect
from apps.shared.utils.json_sanitizer import sanitize_json_data
from apps.shared.utils.logger import get_logger
from apps.shared.utils.sql_utils import validate_read_only_sql

logger = get_logger(__name__)

MAX_DASHBOARD_QUERY_ROWS = 10000
MAX_DASHBOARD_PREVIEW_ROWS = 50
MAX_DASHBOARD_FILTER_OPTIONS = 200


@dataclass
class PreparedAnalyticsQuery:
    """Compiled analytics SQL plus a manager that no longer needs the app DB session."""

    sql: str
    params: dict[str, Any]
    max_rows: int
    db_manager: Any

    async def execute_dataframe(self):
        async with self.db_manager:
            df = await self.db_manager.query(self.sql, params=self.params)
        if self.max_rows is not None and len(df) > self.max_rows:
            return df.head(self.max_rows)
        return df


AXIS_SERIES_CHART_TYPES = {
    "line",
    "bar",
    "area",
    "stacked_bar",
    "grouped_bar",
    "multi_line",
    "multi_area",
}


class DashboardService(TenantAwareService):
    """Service for dashboard CRUD and data querying."""

    def __init__(
        self,
        tenant_id: int,
        dashboard_repo: DashboardRepository,
    ):
        super().__init__(tenant_id)
        self.dashboard_repo = dashboard_repo
        self.artifacts = ArtifactLifecycle(
            db=dashboard_repo.db,
            tenant_id=tenant_id,
            artifact_type=ArtifactType.DASHBOARD,
            entity_repo=dashboard_repo,
        )

    @classmethod
    def create(
        cls,
        tenant_id: int,
        db_session,
    ) -> "DashboardService":
        dashboard_repo = DashboardRepository(db_session)
        return cls(tenant_id, dashboard_repo)

    def _dashboard_guard(self, actor: ActorContext) -> ArtifactAccessGuard:
        return ArtifactAccessGuard(
            db=self.dashboard_repo.db,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            artifact_type=ArtifactType.DASHBOARD.value,
        )

    async def require_read_access(self, *, dashboard_id: int, actor: ActorContext) -> None:
        await self._dashboard_guard(actor).require_read(resource_id=dashboard_id)

    async def require_write_access(self, *, dashboard_id: int, actor: ActorContext) -> None:
        await self._dashboard_guard(actor).require_write(resource_id=dashboard_id)

    async def require_owner_access(self, *, dashboard_id: int, actor: ActorContext) -> None:
        await self._dashboard_guard(actor).require_owner_or_manage(
            resource_id=dashboard_id,
            allow_shared_write=False,
        )

    async def get_dashboard(self, dashboard_id: int) -> DashboardDomain:
        dashboard = await self.dashboard_repo.get_by_id_and_tenant(dashboard_id, self.tenant_id)
        if not dashboard:
            raise ResourceNotFoundError(f"Dashboard not found: {dashboard_id}")
        return dashboard

    async def get_dashboard_for_actor(
        self,
        dashboard_id: int,
        *,
        actor: ActorContext,
    ) -> DashboardDomain:
        await self.require_read_access(dashboard_id=dashboard_id, actor=actor)
        return await self.get_dashboard(dashboard_id)

    async def list_dashboards(
        self,
        user_id: int,
        *,
        has_artifacts_manage: bool = False,
    ) -> list[DashboardDomain]:
        dashboards = await self.artifacts.list_entities(
            user_id=user_id,
            has_manage=has_artifacts_manage,
        )
        return dashboards

    async def list_dashboards_for_actor(self, *, actor: ActorContext) -> list[DashboardDomain]:
        has_manage = await role_has_permission(
            db=self.dashboard_repo.db,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.ARTIFACTS_MANAGE,
        )
        return await self.list_dashboards(
            actor.user_id,
            has_artifacts_manage=has_manage,
        )

    @transaction
    async def create_dashboard(
        self,
        name: str,
        description: str | None,
        config: dict[str, Any] | DashboardConfig,
        owner_id: int,
        thread_id: str | None = None,
    ) -> DashboardCreateWithArtifactResult:
        """Create a new dashboard (tenant-scoped; duplicate name and thread checks)."""
        existing = await self.dashboard_repo.get_by_tenant_and_name(self.tenant_id, name)
        if existing:
            raise DuplicateResourceError(f"Dashboard '{name}' already exists")

        # Convert DashboardConfig to dict for storage if needed
        config_dict = dashboard_config_to_dict(config) if isinstance(config, DashboardConfig) else config

        dashboard = await self.dashboard_repo.create_dashboard(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            config=config_dict,
            owner_id=owner_id,
        )

        artifact: Artifact | None = None
        if thread_id:
            thread_result = await self.dashboard_repo.db.execute(select(ChatThread).where(ChatThread.id == thread_id))
            thread = thread_result.scalar_one_or_none()
            if not thread or thread.tenant_id != self.tenant_id:
                raise ResourceNotFoundError(f"Thread {thread_id} not found")
            if thread.user_id != owner_id:
                raise AuthorizationError("Access denied")

        linked_artifact = await self.artifacts.link_on_create(
            resource_id=dashboard.id,
            owner_id=owner_id,
            title=dashboard.name,
            url=f"/dashboards/{dashboard.id}/embed",
            thread_id=thread_id,
            metadata={"dashboard_id": dashboard.id},
        )
        artifact = Artifact.create_dashboard(linked_artifact)

        return DashboardCreateWithArtifactResult(dashboard=dashboard, artifact=artifact)

    async def create_dashboard_with_auto_link(
        self,
        name: str,
        description: str | None,
        config: dict[str, Any] | DashboardConfig,
        owner_id: int,
        thread_id: str | None = None,
    ) -> DashboardCreateWithArtifactResult:
        """Backward-compatible wrapper for create_dashboard with thread linking."""
        return await self.create_dashboard(
            name=name,
            description=description,
            config=config,
            owner_id=owner_id,
            thread_id=thread_id,
        )

    async def update_dashboard_for_actor(
        self,
        *,
        dashboard_id: int,
        actor: ActorContext,
        name: str | None = None,
        description: str | None = None,
        config: dict[str, Any] | DashboardConfig | None = None,
    ) -> DashboardDomain:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        return await self.update_dashboard(
            dashboard_id=dashboard_id,
            name=name,
            description=description,
            config=config,
        )

    @transaction
    async def update_dashboard(
        self,
        dashboard_id: int,
        name: str | None = None,
        description: str | None = None,
        config: dict[str, Any] | DashboardConfig | None = None,
    ) -> DashboardDomain:
        """Update dashboard fields.

        Args:
            dashboard_id: Dashboard ID
            name: Optional new name
            description: Optional new description
            config: Optional new configuration (dict or DashboardConfig)

        Returns:
            Updated DashboardDomain
        """
        dashboard = await self.dashboard_repo.get_by_id_and_tenant(dashboard_id, self.tenant_id)
        if not dashboard:
            raise ResourceNotFoundError(f"Dashboard not found: {dashboard_id}")

        if name and name != dashboard.name:
            existing = await self.dashboard_repo.get_by_tenant_and_name(self.tenant_id, name)
            if existing:
                raise DuplicateResourceError(f"Dashboard '{name}' already exists")

        # Convert DashboardConfig to dict if needed
        config_dict = None
        if config is not None:
            config_dict = dashboard_config_to_dict(config) if isinstance(config, DashboardConfig) else config

        updated = await self.dashboard_repo.update_fields(
            dashboard_id=dashboard_id,
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            config=config_dict,
        )
        if not updated:
            raise ResourceNotFoundError(f"Dashboard not found: {dashboard_id}")
        return updated

    async def delete_dashboard_for_actor(self, *, dashboard_id: int, actor: ActorContext) -> None:
        await self.require_owner_access(dashboard_id=dashboard_id, actor=actor)
        await self.delete_dashboard(dashboard_id)

    @transaction
    async def delete_dashboard(self, dashboard_id: int) -> None:
        deleted = await self.dashboard_repo.delete_by_id_and_tenant(dashboard_id, self.tenant_id)
        if not deleted:
            raise ResourceNotFoundError(f"Dashboard not found: {dashboard_id}")
        await self.artifacts.delete_cascade(resource_id=dashboard_id)

    # ------------------------------------------------------------------
    # Widget operations
    # ------------------------------------------------------------------

    async def add_widget_for_actor(
        self,
        *,
        dashboard_id: int,
        actor: ActorContext,
        widget_type: WidgetType,
        chart_type: ChartType | None = None,
        position: WidgetPosition | None = None,
        data_source_id: int | None = None,
        query: str | None = None,
        field_mapping: FieldMapping | None = None,
        display_config: ChartDisplayConfig | None = None,
    ) -> DashboardWidget:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_config = dashboard.config

        _validate_widget_semantics(
            widget_type=widget_type,
            chart_type=chart_type,
            field_mapping=field_mapping,
            query=query,
            data_source_id=data_source_id,
        )

        if query:
            compile_query(query, filters=dashboard_config.filters, dialect=None)

        widget_id = f"widget-{uuid.uuid4().hex[:8]}"
        if position is None:
            max_y = 0
            for w in dashboard_config.widgets:
                max_y = max(max_y, w.position.y + w.position.h)
            position = WidgetPosition(x=0, y=max_y, w=dashboard_config.layout.cols, h=6)

        if field_mapping and (not display_config or not display_config.series_labels):
            inferred = _infer_series_labels_from_field_mapping(field_mapping)
            if display_config is None:
                display_config = ChartDisplayConfig()
            if inferred and not display_config.series_labels:
                display_config.series_labels = inferred

        new_widget = DashboardWidget(
            id=widget_id,
            type=widget_type,
            position=position,
            chart_type=chart_type,
            display_config=display_config,
            options=None,
            data_source_id=data_source_id,
            query=query,
            field_mapping=field_mapping,
        )
        dashboard_config.widgets.append(new_widget)
        await self.update_dashboard(dashboard_id=dashboard_id, config=dashboard_config)
        return new_widget

    async def update_widget_for_actor(
        self,
        *,
        dashboard_id: int,
        widget_id: str,
        actor: ActorContext,
        chart_type: ChartType | None = None,
        position: WidgetPosition | None = None,
        data_source_id: int | None = None,
        query: str | None = None,
        field_mapping: FieldMapping | None = None,
        display_config: ChartDisplayConfig | None = None,
    ) -> DashboardWidget:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_config = dashboard.config

        target_widget = _resolve_widget_by_id(dashboard_config.widgets, widget_id)
        if not target_widget:
            raise ResourceNotFoundError(f"Widget '{widget_id}' not found in dashboard {dashboard_id}")

        effective_query = query if query is not None else target_widget.query
        effective_data_source_id = data_source_id if data_source_id is not None else target_widget.data_source_id
        effective_field_mapping = field_mapping if field_mapping is not None else target_widget.field_mapping
        effective_chart_type = chart_type if chart_type is not None else target_widget.chart_type

        _validate_widget_semantics(
            widget_type=target_widget.type,
            chart_type=effective_chart_type,
            field_mapping=effective_field_mapping,
            query=effective_query,
            data_source_id=effective_data_source_id,
        )

        if query is not None:
            try:
                compile_query(query, filters=dashboard_config.filters, dialect=None)
            except ValidationError:
                raise
            target_widget.query = query

        if chart_type is not None:
            target_widget.chart_type = chart_type
        if position is not None:
            target_widget.position = position
        if data_source_id is not None:
            target_widget.data_source_id = data_source_id
        if field_mapping is not None:
            target_widget.field_mapping = field_mapping
        if display_config is not None:
            target_widget.display_config = display_config

        await self.update_dashboard(dashboard_id=dashboard_id, config=dashboard_config)
        return target_widget

    async def remove_widget_for_actor(
        self,
        *,
        dashboard_id: int,
        widget_id: str,
        actor: ActorContext,
    ) -> DashboardDomain:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_config = dashboard.config

        target_widget = _resolve_widget_by_id(dashboard_config.widgets, widget_id)
        if not target_widget:
            raise ResourceNotFoundError(f"Widget '{widget_id}' not found in dashboard {dashboard_id}")

        dashboard_config.widgets = [w for w in dashboard_config.widgets if w.id != widget_id]
        return await self.update_dashboard(dashboard_id=dashboard_id, config=dashboard_config)

    # ------------------------------------------------------------------
    # Filter operations
    # ------------------------------------------------------------------

    async def add_filter_for_actor(
        self,
        *,
        dashboard_id: int,
        actor: ActorContext,
        name: str,
        filter_type: FilterType,
        param_key: str | None = None,
        value: Any | None = None,
        data_source_id: int | None = None,
        options_query: str | None = None,
        options: list[DashboardFilterOption] | None = None,
        allow_multiple: bool | None = None,
        time_precision: TimePrecision | None = None,
        description: str | None = None,
        required: bool = False,
        validate_options_query: bool = False,
        data_source_service: DataSourceService | None = None,
    ) -> DashboardFilter:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_config = dashboard.config

        filter_id = f"filter-{uuid.uuid4().hex[:8]}"
        new_filter = DashboardFilter(
            id=filter_id,
            name=name,
            type=filter_type,
            param_key=param_key,
            value=value,
            data_source_id=data_source_id,
            options_query=options_query,
            options=options,
            allow_multiple=allow_multiple,
            time_precision=time_precision,
            description=description,
            required=required,
        )
        _validate_filter_macro_config(new_filter)
        if validate_options_query and new_filter.type == "dropdown_datasource":
            await self._validate_datasource_filter_options_query(
                dashboard_filter=new_filter,
                data_source_service=data_source_service,
                user_id=actor.user_id,
                user_role=actor.user_role,
            )
        if dashboard_config.filters is None:
            dashboard_config.filters = []
        dashboard_config.filters.append(new_filter)
        await self.update_dashboard(dashboard_id=dashboard_id, config=dashboard_config)
        return new_filter

    async def update_filter_for_actor(
        self,
        *,
        dashboard_id: int,
        filter_id: str,
        actor: ActorContext,
        field_updates: dict[str, Any],
        validate_options_query: bool = False,
        data_source_service: DataSourceService | None = None,
    ) -> DashboardFilter:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_config = dashboard.config

        dashboard_filter = dashboard_config.get_filter_by_id(filter_id)
        if not dashboard_filter:
            raise ResourceNotFoundError(f"Filter '{filter_id}' not found in dashboard {dashboard_id}")

        for field, val in field_updates.items():
            setattr(dashboard_filter, field, val)

        _validate_filter_macro_config(dashboard_filter)

        should_validate_options_query = (
            validate_options_query
            and dashboard_filter.type == "dropdown_datasource"
            and ("options_query" in field_updates or "data_source_id" in field_updates or "type" in field_updates)
        )

        if should_validate_options_query:
            await self._validate_datasource_filter_options_query(
                dashboard_filter=dashboard_filter,
                data_source_service=data_source_service,
                user_id=actor.user_id,
                user_role=actor.user_role,
            )

        await self.update_dashboard(dashboard_id=dashboard_id, config=dashboard_config)
        return dashboard_filter

    async def remove_filter_for_actor(
        self,
        *,
        dashboard_id: int,
        filter_id: str,
        actor: ActorContext,
    ) -> DashboardDomain:
        await self.require_write_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_config = dashboard.config

        if not dashboard_config.filters:
            raise ResourceNotFoundError(f"Filter '{filter_id}' not found in dashboard {dashboard_id}")

        before_count = len(dashboard_config.filters)
        dashboard_config.filters = [f for f in dashboard_config.filters if f.id != filter_id]
        if len(dashboard_config.filters) == before_count:
            raise ResourceNotFoundError(f"Filter '{filter_id}' not found in dashboard {dashboard_id}")

        return await self.update_dashboard(dashboard_id=dashboard_id, config=dashboard_config)

    # ------------------------------------------------------------------
    # Data query operations
    # ------------------------------------------------------------------

    async def query_widget_data(
        self,
        widget: DashboardWidget,
        data_source_service: DataSourceService,
        user_id: int,
        user_role: str | None,
        filters: list[DashboardFilter] | None = None,
    ) -> list[dict[str, Any]]:
        """Query data for a specific widget.

        Args:
            widget: Widget domain model (with query and data_source_id)
            data_source_service: Data source service instance
            user_id: Request user ID for ABAC checks
            user_role: Request user role for ABAC checks

        Returns:
            List of data records as dictionaries
        """
        df = await self._query_widget_dataframe(
            widget=widget,
            data_source_service=data_source_service,
            user_id=user_id,
            user_role=user_role,
            filters=filters,
        )
        return self.materialize_widget_rows(df)

    async def prepare_widget_analytics_query(
        self,
        widget: DashboardWidget,
        data_source_service: DataSourceService,
        user_id: int,
        user_role: str | None,
        filters: list[DashboardFilter] | None = None,
        max_rows: int = MAX_DASHBOARD_QUERY_ROWS,
    ) -> PreparedAnalyticsQuery:
        """Authz + compile + build manager. Caller should close the app DB session before execute."""
        compiled = await self._compile_widget_query(
            widget=widget,
            data_source_service=data_source_service,
            user_id=user_id,
            user_role=user_role,
            filters=filters,
        )
        if not widget.data_source_id:
            raise ValidationError(f"Widget '{widget.id}' has no data source for query")
        await data_source_service.require_read_access_for_actor(
            data_source_id=widget.data_source_id,
            actor=ActorContext(
                tenant_id=self.tenant_id,
                user_id=user_id,
                user_role=user_role,
            ),
        )
        db_manager = await data_source_service.get_db_manager(widget.data_source_id)
        return PreparedAnalyticsQuery(
            sql=compiled.sql,
            params=compiled.params,
            max_rows=max_rows,
            db_manager=db_manager,
        )

    @staticmethod
    def materialize_widget_rows(df) -> list[dict[str, Any]]:
        if df.empty:
            return []
        return sanitize_json_data(df.to_dict(orient="records"))

    async def query_widget_preview(
        self,
        widget: DashboardWidget,
        data_source_service: DataSourceService,
        user_id: int,
        user_role: str | None,
        limit: int = 50,
        filters: list[DashboardFilter] | None = None,
    ) -> dict[str, Any]:
        """Query preview data and column metadata for a specific widget.

        Args:
            widget: Widget domain model (with query and data_source_id)
            data_source_service: Data source service instance
            user_id: Request user ID for ABAC checks
            user_role: Request user role for ABAC checks
            limit: Maximum rows to return in preview

        Returns:
            Dict with columns metadata and preview rows
        """
        safe_limit = max(1, min(limit, MAX_DASHBOARD_PREVIEW_ROWS))
        try:
            df = await self._query_widget_dataframe(
                widget=widget,
                data_source_service=data_source_service,
                user_id=user_id,
                user_role=user_role,
                filters=filters,
                max_rows=safe_limit,
            )

            if df.empty:
                return {"columns": [], "rows": []}
        except Exception as e:
            raise SQLPreviewError(f"Error during SQL preview execution: {str(e)}") from e

        preview_df = df.head(safe_limit)
        rows = sanitize_json_data(preview_df.to_dict(orient="records"))
        columns = [{"name": str(col), "type": str(dtype)} for col, dtype in preview_df.dtypes.items()]

        return {"columns": columns, "rows": rows}

    async def preview_dashboard_sql_for_actor(
        self,
        *,
        dashboard_id: int,
        data_source_id: int,
        query: str,
        actor: ActorContext,
        data_source_service: DataSourceService,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Compile dashboard filter macros and execute SQL preview (limited rows)."""
        dashboard = await self.get_dashboard_for_actor(dashboard_id=dashboard_id, actor=actor)
        preview_widget = DashboardWidget(
            id="_sql_preview",
            type="metric",
            position=WidgetPosition(x=0, y=0, w=1, h=1),
            data_source_id=data_source_id,
            query=query,
        )
        return await self._preview_dashboard_widget_with_filters(
            preview_widget=preview_widget,
            filters=dashboard.config.filters,
            data_source_service=data_source_service,
            actor=actor,
            limit=limit,
        )

    async def preview_dashboard_widget_sql_for_actor(
        self,
        *,
        dashboard_id: int,
        widget_id: str,
        actor: ActorContext,
        data_source_service: DataSourceService,
        limit: int = 50,
        query: str | None = None,
        data_source_id: int | None = None,
    ) -> dict[str, Any]:
        """Compile filter macros and execute preview for an existing widget (optional SQL/datasource overrides)."""
        dashboard = await self.get_dashboard_for_actor(dashboard_id=dashboard_id, actor=actor)
        widget = dashboard.get_widget_by_id(widget_id)
        if not widget:
            raise ResourceNotFoundError(f"Widget '{widget_id}' not found in dashboard {dashboard_id}")

        merged_query = query if query is not None else widget.query
        merged_ds = data_source_id if data_source_id is not None else widget.data_source_id
        preview_widget = replace(widget, query=merged_query, data_source_id=merged_ds)
        if not preview_widget.query:
            raise ValidationError(f"Widget '{widget_id}' has no query for preview")
        if not preview_widget.data_source_id:
            raise ValidationError(f"Widget '{widget_id}' has no data source for preview")

        return await self._preview_dashboard_widget_with_filters(
            preview_widget=preview_widget,
            filters=dashboard.config.filters,
            data_source_service=data_source_service,
            actor=actor,
            limit=limit,
        )

    async def _preview_dashboard_widget_with_filters(
        self,
        *,
        preview_widget: DashboardWidget,
        filters: list[DashboardFilter] | None,
        data_source_service: DataSourceService,
        actor: ActorContext,
        limit: int,
    ) -> dict[str, Any]:
        """Execute preview for an effective widget with dashboard filters."""
        return await self.query_widget_preview(
            preview_widget,
            data_source_service=data_source_service,
            user_id=actor.user_id,
            user_role=actor.user_role,
            limit=limit,
            filters=filters,
        )

    async def _query_filter_options(
        self,
        dashboard_filter: DashboardFilter,
        data_source_service: DataSourceService,
        user_id: int,
        user_role: str | None,
        limit: int = MAX_DASHBOARD_FILTER_OPTIONS,
    ) -> list[dict[str, Any]]:
        """Query options for a dropdown filter."""
        if dashboard_filter.type != "dropdown_datasource":
            raise ValidationError("Filter type does not support data source options")

        if not dashboard_filter.options_query:
            raise ValidationError("Filter options query is required")

        validate_read_only_sql(dashboard_filter.options_query)

        # Options query is treated as plain SQL authored by user/agent.
        query = dashboard_filter.options_query
        normalized = " ".join(query.strip().split()).lower()
        if " limit " not in f" {normalized} ":
            query = f"{query.rstrip()} LIMIT {limit}"
        df = await data_source_service.query_data_for_actor(
            data_source_id=dashboard_filter.data_source_id,
            actor=ActorContext(
                tenant_id=self.tenant_id,
                user_id=user_id,
                user_role=user_role,
            ),
            sql_query=query,
            max_rows=limit,
        )

        if df.empty:
            return []

        rows = df.head(limit).to_dict(orient="records")
        columns = list(df.columns)

        options: list[dict[str, Any]] = []
        if "value" in df.columns and "label" in df.columns:
            for row in rows:
                options.append({"value": row.get("value"), "label": str(row.get("label", ""))})
            return options

        if len(columns) == 1:
            col = columns[0]
            for row in rows:
                value = row.get(col)
                options.append({"value": value, "label": str(value)})
            return options

        for row in rows:
            value = row.get(columns[0])
            label = row.get(columns[1])
            options.append({"value": value, "label": str(label)})
        return options

    async def get_filter_options_for_actor(
        self,
        *,
        dashboard_id: int,
        filter_id: str,
        actor: ActorContext,
        data_source_service: DataSourceService,
    ) -> DashboardFilterOptionsResult:
        await self.require_read_access(dashboard_id=dashboard_id, actor=actor)
        dashboard = await self.get_dashboard(dashboard_id)
        dashboard_filter = dashboard.config.get_filter_by_id(filter_id)
        if not dashboard_filter:
            raise ResourceNotFoundError(f"Filter '{filter_id}' not found in dashboard {dashboard_id}")

        if dashboard_filter.type == "dropdown_static":
            return DashboardFilterOptionsResult(options=dashboard_filter.options or [])

        if dashboard_filter.type != "dropdown_datasource":
            return DashboardFilterOptionsResult(options=[])

        if not dashboard_filter.options_query:
            return DashboardFilterOptionsResult(options=[])

        try:
            queried_options = await self._query_filter_options(
                dashboard_filter=dashboard_filter,
                data_source_service=data_source_service,
                user_id=actor.user_id,
                user_role=actor.user_role,
            )
            return DashboardFilterOptionsResult(
                options=[
                    DashboardFilterOption(label=option["label"], value=option["value"]) for option in queried_options
                ]
            )
        except ValidationError as exc:
            logger.warning(
                "Failed to load dashboard filter options (dashboard_id=%s, filter_id=%s): %s",
                dashboard_id,
                filter_id,
                str(exc),
            )
            return DashboardFilterOptionsResult(
                options=[],
                has_error=True,
                error_message=f"Filter options query failed: {str(exc)}",
            )
        except Exception as exc:
            logger.exception(
                "Unexpected error while loading dashboard filter options (dashboard_id=%s, filter_id=%s)",
                dashboard_id,
                filter_id,
            )
            return DashboardFilterOptionsResult(
                options=[],
                has_error=True,
                error_message=f"Filter options query failed: {str(exc)}",
            )

    async def _validate_datasource_filter_options_query(
        self,
        dashboard_filter: DashboardFilter,
        data_source_service: DataSourceService | None,
        user_id: int | None,
        user_role: str | None,
    ) -> None:
        if dashboard_filter.type != "dropdown_datasource":
            return
        if not dashboard_filter.options_query:
            raise ValidationError("Filter options query is required")
        if not dashboard_filter.data_source_id:
            raise ValidationError("Data source is required for dropdown data source filter")
        if data_source_service is None or user_id is None:
            raise ValidationError("Cannot validate filter options query without request context")

        try:
            await self._query_filter_options(
                dashboard_filter=dashboard_filter,
                data_source_service=data_source_service,
                user_id=user_id,
                user_role=user_role,
                limit=1,
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Filter options query execution failed: {str(exc)}") from exc

    async def _compile_widget_query(
        self,
        widget: DashboardWidget,
        data_source_service: DataSourceService,
        user_id: int,
        user_role: str | None,
        filters: list[DashboardFilter] | None,
    ):
        if not widget.query or not widget.data_source_id:
            raise ValidationError(f"Widget '{widget.id}' has no data binding configured")

        validate_read_only_sql(widget.query)

        query_dialect = await self._get_query_dialect(
            data_source_service,
            widget.data_source_id,
            user_id=user_id,
            user_role=user_role,
        )
        return compile_query(widget.query, filters=filters, dialect=query_dialect)

    async def _query_widget_dataframe(
        self,
        widget: DashboardWidget,
        data_source_service: DataSourceService,
        user_id: int,
        user_role: str | None,
        filters: list[DashboardFilter] | None,
        max_rows: int = MAX_DASHBOARD_QUERY_ROWS,
    ):
        compiled = await self._compile_widget_query(
            widget=widget,
            data_source_service=data_source_service,
            user_id=user_id,
            user_role=user_role,
            filters=filters,
        )

        return await data_source_service.query_data_for_actor(
            data_source_id=widget.data_source_id,
            actor=ActorContext(
                tenant_id=self.tenant_id,
                user_id=user_id,
                user_role=user_role,
            ),
            sql_query=compiled.sql,
            params=compiled.params,
            max_rows=max_rows,
        )

    async def _get_query_dialect(
        self,
        data_source_service: DataSourceService,
        data_source_id: int,
        *,
        user_id: int,
        user_role: str | None,
    ) -> SQLDialectStr | None:
        actor = ActorContext(
            tenant_id=self.tenant_id,
            user_id=user_id,
            user_role=user_role,
        )
        try:
            data_source = await data_source_service.get_data_source_for_actor(
                data_source_id=data_source_id,
                actor=actor,
            )
        except (AuthorizationError, ResourceNotFoundError):
            return None
        if not data_source:
            return None
        return resolve_sql_dialect(data_source.type)


# ---------------------------------------------------------------------------
# Module-level helpers (no state, shared by service methods)
# ---------------------------------------------------------------------------


def apply_filter_value_overrides(
    filters: list[DashboardFilter] | None,
    overrides: list[DashboardFilterValueOverrideDTO] | None,
) -> list[DashboardFilter] | None:
    """Return dashboard filters with request-time values applied."""
    if not filters or not overrides:
        return filters

    by_id = {override.id: override for override in overrides if override.id}
    by_param_key = {override.param_key: override for override in overrides if override.param_key}

    merged: list[DashboardFilter] = []
    for dashboard_filter in filters:
        override = by_id.get(dashboard_filter.id)
        if override is None and dashboard_filter.param_key:
            override = by_param_key.get(dashboard_filter.param_key)
        if override is None:
            merged.append(dashboard_filter)
            continue
        merged.append(replace(dashboard_filter, value=override.value))
    return merged


def _resolve_widget_by_id(widgets: list[DashboardWidget], widget_id: str) -> DashboardWidget | None:
    """Return the widget with the given ID, or None."""
    for widget in widgets:
        if widget.id == widget_id:
            return widget
    return None


def _validate_filter_macro_config(dashboard_filter: DashboardFilter) -> None:
    """Validate that param_key is well-formed for macro-supported filter types.

    Raises ValidationError with a descriptive message when the param_key
    is missing or syntactically invalid.
    """
    if dashboard_filter.type not in ("time_range", "dropdown_static", "dropdown_datasource"):
        return
    try:
        dashboard_filter.get_param_names()
    except ValueError as exc:
        raise ValidationError(f"Filter '{dashboard_filter.name}' has an invalid param_key: {exc}") from exc


def _infer_label_from_column_name(column_name: str) -> str:
    """Convert snake_case or camelCase column name to Title Case label.

    Examples:
        "daily_sales"    -> "Daily Sales"
        "orderCount"     -> "Order Count"
    """
    if not column_name:
        return ""
    label = column_name.replace("_", " ")
    result = []
    for i, char in enumerate(label):
        if i > 0 and char.isupper() and label[i - 1].islower():
            result.append(" ")
        result.append(char)
    return "".join(result).title()


def _infer_series_labels_from_field_mapping(field_mapping: FieldMapping | None) -> dict[str, str] | None:
    """Infer display labels from field mapping series column names."""
    if not field_mapping or not field_mapping.series:
        return None
    series_labels = {}
    if isinstance(field_mapping.series, list):
        for item in field_mapping.series:
            if isinstance(item, str):
                series_labels[item] = _infer_label_from_column_name(item)
            elif isinstance(item, dict) and "name" in item:
                col_name = item["name"]
                series_labels[col_name] = _infer_label_from_column_name(col_name)
    return series_labels if series_labels else None


def _validate_widget_semantics(
    widget_type: WidgetType,
    chart_type: ChartType | None,
    field_mapping: FieldMapping | None,
    query: str | None,
    data_source_id: int | None,
) -> None:
    """Validate widget/chart/mapping contracts used by both API and agent tools.

    This guard keeps dashboard configuration semantics deterministic for agents,
    so invalid combinations fail fast at write time instead of surfacing later in
    query/preview/render steps.
    """
    # if query and not data_source_id:
    #    raise ValidationError("Widget with query requires data_source_id")

    # Keep backward-compatible authoring flow: users/agents may save query first
    # and bind data source later. Runtime query execution still requires both.

    if widget_type == "chart":
        if chart_type is None:
            raise ValidationError("Chart widget requires chart_type")
    elif chart_type is not None:
        raise ValidationError("Only chart widgets can set chart_type")

    if widget_type != "chart" or chart_type is None:
        return

    if chart_type in AXIS_SERIES_CHART_TYPES:
        if not field_mapping or not field_mapping.x_axis:
            raise ValidationError(f"Chart type '{chart_type}' requires field_mapping.x_axis")
        if not field_mapping.series or not isinstance(field_mapping.series, list) or len(field_mapping.series) == 0:
            raise ValidationError(f"Chart type '{chart_type}' requires non-empty field_mapping.series")
        return

    if chart_type == "scatter":
        if not field_mapping or not field_mapping.x_axis or not field_mapping.y_axis:
            raise ValidationError("Chart type 'scatter' requires field_mapping.x_axis and field_mapping.y_axis")
        return

    if chart_type == "heatmap":
        if not field_mapping or not field_mapping.x_axis or not field_mapping.y_axis or not field_mapping.value:
            raise ValidationError(
                "Chart type 'heatmap' requires field_mapping.x_axis, field_mapping.y_axis, and field_mapping.value"
            )
        return

    if chart_type == "gauge":
        if not field_mapping or not field_mapping.value:
            raise ValidationError("Chart type 'gauge' requires field_mapping.value")
        return

    if chart_type == "pie":
        has_value_field = bool(field_mapping and field_mapping.value)
        has_legacy_series_mapping = _is_legacy_pie_series_mapping(field_mapping)
        if not has_value_field and not has_legacy_series_mapping:
            raise ValidationError(
                "Chart type 'pie' requires field_mapping.value (preferred) or legacy series mapping with name/value"
            )


def _is_legacy_pie_series_mapping(field_mapping: FieldMapping | None) -> bool:
    """Return True when field_mapping uses legacy pie series descriptor format.

    Legacy format example:
        {"series": [{"name": "label_col", "value": "metric_col"}]}
    """
    if not field_mapping or not isinstance(field_mapping.series, list) or not field_mapping.series:
        return False
    first = field_mapping.series[0]
    return isinstance(first, dict) and bool(first.get("name")) and bool(first.get("value"))
