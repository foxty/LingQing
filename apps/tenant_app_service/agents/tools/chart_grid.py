"""Multi-panel chart grid tools for agent reports."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.chart.grid import render_chart_grid
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.chart_support import (
    assert_data_source_allowed,
    chart_tool_success,
    exception_detail,
    is_sql_empty_result,
    query_sql_as_json_records,
    register_agent_chart,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


@tool
async def create_chart_grid_from_structured_data(
    data: str,
    title: str,
    panels: str,
    rows: int = 2,
    cols: int = 2,
    subtitle: str | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Render a small-multiples grid (e.g. 2×2) from one JSON dataset in a single image.

    Args:
        data: JSON array of row objects shared by all panels
        title: Overall figure title
        panels: JSON array of panel specs: chart_type, title, x_key, y_key, row, col
        rows: Grid row count (default 2)
        cols: Grid column count (default 2)
        subtitle: Optional subtitle under the title
        config: Runtime configuration (auto-injected)
    """
    logger.info("Creating chart grid: title=%s rows=%s cols=%s", title, rows, cols)
    try:
        runtime = extract_runtime_context(config)
        rendered = render_chart_grid(
            data=data,
            title=title,
            panels=panels,
            rows=rows,
            cols=cols,
            subtitle=subtitle,
        )
        markdown = await register_agent_chart(rendered=rendered, runtime=runtime)
        return chart_tool_success(markdown)
    except ValueError as e:
        return ToolResult.error_result(code="CHART_GRID_VALIDATION_ERROR", message=str(e))
    except Exception as e:
        detail = exception_detail(e)
        logger.error("Chart grid failed: %s", detail, exc_info=True)
        return ToolResult.error_result(
            code="CHART_GRID_CREATE_FAILED",
            message=f"Error creating chart grid: {detail}",
        )


@tool
async def create_chart_grid_from_sql(
    data_source_id: int,
    sql_query: str,
    title: str,
    panels: str,
    rows: int = 2,
    cols: int = 2,
    subtitle: str | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Render a small-multiples grid from SQL rows (one SELECT returning columns for all panels)."""
    runtime = extract_runtime_context(config)
    denied = assert_data_source_allowed(runtime=runtime, data_source_id=data_source_id)
    if denied is not None:
        return denied

    data_json, err = await query_sql_as_json_records(
        runtime=runtime,
        data_source_id=data_source_id,
        sql_query=sql_query,
    )
    if err is not None:
        if is_sql_empty_result(err):
            return ToolResult.error_result(
                code="CHART_SQL_EMPTY_RESULT",
                message=f"Query returned no data for chart grid '{title}'",
            )
        return err

    try:
        rendered = render_chart_grid(
            data=data_json,
            title=title,
            panels=panels,
            rows=rows,
            cols=cols,
            subtitle=subtitle,
        )
        markdown = await register_agent_chart(rendered=rendered, runtime=runtime)
        return chart_tool_success(markdown)
    except ValueError as e:
        return ToolResult.error_result(code="CHART_GRID_VALIDATION_ERROR", message=str(e))
    except Exception as e:
        detail = exception_detail(e)
        logger.error("Chart grid from SQL failed: %s", detail, exc_info=True)
        return ToolResult.error_result(
            code="CHART_GRID_CREATE_FROM_SQL_FAILED",
            message=f"Error creating chart grid from SQL: {detail}",
        )
