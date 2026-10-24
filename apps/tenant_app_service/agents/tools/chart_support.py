"""Shared helpers for agent axis chart tools."""

from __future__ import annotations

import json

from apps.shared.chart.service import ChartService
from apps.shared.chart.types import ChartRenderResult
from apps.shared.data_source import DataSourceService
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import AgentRuntimeContext
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)

_SQL_CHART_ROW_CAP = 500


def exception_detail(exc: BaseException) -> str:
    msg = str(exc).strip()
    if msg:
        return msg
    if exc.__cause__ is not None:
        cause_msg = str(exc.__cause__).strip()
        if cause_msg:
            return f"{type(exc).__name__}: {cause_msg}"
    return type(exc).__name__


def is_sql_empty_result(err: ToolResult) -> bool:
    return err.error is not None and err.error.code == "CHART_SQL_EMPTY_RESULT"


def chart_render_kwargs(
    *,
    chart_type: str,
    data: str,
    title: str,
    x_label: str | None = None,
    y_label: str | None = None,
    x_key: str | None = None,
    y_key: str | None = None,
    series_key: str | None = None,
    series_keys: list[str] | None = None,
    z_key: str | None = None,
    stacked: bool = False,
    subtitle: str | None = None,
    reference_lines_json: str | None = None,
    annotations_json: str | None = None,
    y_axis_percent: bool = False,
    measure_key: str | None = None,
) -> dict:
    """Keyword args for ``render_chart`` shared by chart agent tools."""
    return {
        "chart_type": chart_type,
        "data": data,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "x_key": x_key,
        "y_key": y_key,
        "series_key": series_key,
        "series_keys": series_keys,
        "z_key": z_key,
        "stacked": stacked,
        "subtitle": subtitle,
        "reference_lines_json": reference_lines_json,
        "annotations_json": annotations_json,
        "y_axis_percent": y_axis_percent,
        "measure_key": measure_key,
    }


def chart_tool_success(markdown: str) -> ToolResult:
    return ToolResult.success(
        markdown,
        metadata={"raw_result": {"markdown": markdown}},
    )


async def register_agent_chart(*, rendered: ChartRenderResult, runtime: AgentRuntimeContext) -> str:
    async with app_db_session() as session:
        service = ChartService.create(tenant_id=runtime.user.tenant_id, db=session)
        return await service.register_chart(
            svg_bytes=rendered.svg_bytes,
            png_bytes=rendered.png_bytes,
            owner_id=runtime.user.user_id,
            thread_id=runtime.thread_id,
            title=rendered.title,
        )


def assert_data_source_allowed(*, runtime: AgentRuntimeContext, data_source_id: int) -> ToolResult | None:
    profile = runtime.capability_profile
    if profile and profile.allowed_data_source_ids is not None and data_source_id not in profile.allowed_data_source_ids:
        return ToolResult.error_result("Data source is not assigned to this agent", code="PERMISSION_DENIED")
    return None


async def query_sql_as_json_records(
    *,
    runtime: AgentRuntimeContext,
    data_source_id: int,
    sql_query: str,
    max_rows: int = _SQL_CHART_ROW_CAP,
) -> tuple[str | None, ToolResult | None]:
    """Run SELECT for chart tools. Returns (json_data, error_result)."""
    tenant_id = runtime.user.tenant_id
    try:
        async with app_db_session() as session:
            service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=DataSourceRepository(session),
                asset_repo=AssetMetadataRepository(session),
            )
            df = await service.query_data_for_actor(
                data_source_id=data_source_id,
                sql_query=sql_query,
                actor=ActorContext(
                    tenant_id=tenant_id,
                    user_id=runtime.user.user_id,
                    user_role=runtime.user.role,
                ),
            )
    except Exception as exc:
        detail = exception_detail(exc)
        logger.error("Chart SQL query failed: %s", detail, exc_info=True)
        return None, ToolResult.error_result(
            code="CHART_SQL_QUERY_FAILED",
            message=f"Error running SQL for chart: {detail}",
            hint="Check SQL syntax, column names, and data-source permissions.",
        )

    if df.empty:
        return None, ToolResult.error_result(
            code="CHART_SQL_EMPTY_RESULT",
            message="Query returned no data for chart",
        )

    if len(df) > max_rows:
        logger.warning("Query returned %d rows, truncating to %d for chart", len(df), max_rows)
        df = df.head(max_rows)

    return json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str), None

