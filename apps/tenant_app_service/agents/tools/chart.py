"""Chart tool wrappers for agents.

Rendering logic lives in apps.shared.chart.renderer.  These tools are thin
adapters that wire LangGraph tool inputs to render_chart() and manage the
DB session for data-source queries.
"""

import json
from typing import List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.chart.renderer import render_chart
from apps.shared.data_source import DataSourceService
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import delegated_data_source_ids, extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


@tool
def create_chart_from_structured_data(
    chart_type: str,
    data: str,
    title: str,
    x_label: str | None = None,
    y_label: str | None = None,
    x_key: str | None = None,
    y_key: str | None = None,
    series_key: str | None = None,
    series_keys: List[str] | None = None,
    z_key: str | None = None,
    stacked: bool = False,
    config: RunnableConfig | None = None,
) -> ToolResult:
    """Create a chart (SVG) using Plotly from structured data.

    Args:
        chart_type: Type of chart — 'bar', 'line', 'pie', 'scatter', 'area', 'heatmap'.
            Add series_key or series_keys to make bar/line/area/scatter multi-series.
        data: JSON string of a list of dicts, e.g. '[{"month":"Jan","sales":100}, ...]'
        title: Chart title
        x_label: X-axis label (defaults to x_key)
        y_label: Y-axis label (defaults to y_key or first series_key)
        x_key: Column for X-axis (auto-detected from first column if omitted)
        y_key: Column for Y values (single-series); row-label column for heatmap
        series_keys: Column names for multiple Y series (bar/line multi-series).
            Accepts BOTH wide format (series as columns) and long format (series as values
            in a category column) — auto-pivoted if needed.
            Example: ["product_A", "product_B", "product_C"]
        z_key: Column for Z values (heatmap only — the numeric intensity)
        stacked: When True and chart_type='bar', renders as stacked bar instead of grouped
        config: Runtime configuration (auto-injected by LangGraph)

    Returns:
        Markdown string with chart image

    Examples:
        # Single-series bar
        create_chart_from_structured_data(
            chart_type="bar", data='[{"month":"Jan","sales":100},{"month":"Feb","sales":120}]',
            x_key="month", y_key="sales", title="Monthly Sales")

        # Multi-series bar using series_key (long format — PREFERRED)
        create_chart_from_structured_data(
            chart_type="bar",
            data='[{"month":"Jan","product":"A","sales":100},{"month":"Jan","product":"B","sales":80}]',
            x_key="month", y_key="sales", series_key="product", title="Sales by Product")

        # Stacked bar
        create_chart_from_structured_data(
            chart_type="bar", stacked=True,
            data='[{"month":"Jan","product":"A","sales":100},{"month":"Jan","product":"B","sales":80}]',
            x_key="month", y_key="sales", series_key="product", title="Stacked Sales")

        # Multi-series line
        create_chart_from_structured_data(
            chart_type="line",
            data='[{"month":"Jan","product":"A","sales":100},{"month":"Jan","product":"B","sales":80}]',
            x_key="month", y_key="sales", series_key="product", title="Monthly Trend")

        # Scatter colored by category
        create_chart_from_structured_data(
            chart_type="scatter",
            data='[{"price":10,"qty":5,"cat":"A"},{"price":20,"qty":8,"cat":"B"}]',
            x_key="price", y_key="qty", series_key="cat", title="Price vs Qty")

        # Heatmap
        create_chart_from_structured_data(
            chart_type="heatmap",
            data='[{"product":"A","month":"Jan","sales":100}]',
            x_key="month", y_key="product", z_key="sales", title="Sales Heatmap")
    """
    logger.info(f"Creating static Plotly chart: type={chart_type}, title={title}")
    try:
        result = render_chart(
            chart_type=chart_type,
            data=data,
            title=title,
            x_label=x_label,
            y_label=y_label,
            x_key=x_key,
            y_key=y_key,
            series_key=series_key,
            series_keys=series_keys,
            z_key=z_key,
            stacked=stacked,
        )
        logger.info(f"Static chart created: {title}")
        return ToolResult.success({"markdown": result})

    except Exception as e:
        logger.error(f"Error creating static Plotly chart: {str(e)}", exc_info=True)
        return ToolResult.error_result(
            code="CHART_CREATE_FROM_STRUCTURED_DATA_FAILED",
            message=f"Error creating chart: {str(e)}",
        )


@tool
async def create_chart_from_sql(
    data_source_id: int,
    sql_query: str,
    chart_type: str,
    x_key: str,
    title: str,
    y_key: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    series_key: str | None = None,
    series_keys: List[str] | None = None,
    z_key: str | None = None,
    stacked: bool = False,
    config: RunnableConfig = None,
) -> ToolResult:
    """Create chart from SQL query results.

    Args:
        data_source_id: Data source ID
        sql_query: SQL SELECT query (≤100 rows recommended for readability)
        chart_type: 'bar'|'line'|'pie'|'scatter'|'area'|'heatmap'.
            Provide series_keys to make 'bar' or 'line' multi-series.
        x_key: Column for X-axis
        title: Chart title
        y_key: Column for Y values (single-series or multi-series value column); row-label column for heatmap
        x_label: X-axis label (defaults to x_key)
        y_label: Y-axis label (defaults to y_key)
        series_key: [PREFERRED for multi-series] A single column name whose distinct values define
            the series. The tool auto-detects all distinct values and pivots the data.
            Use this when your SQL returns long-format data with a category column.
            Example: series_key="product" (column contains "Product 1", "Product 2", ...)
            Supports bar, line, area, and scatter chart types.
        series_keys: Explicit list of series names (advanced). Use when you know the exact values
            or column names upfront. Supports wide-format data (series as columns) and
            long-format data (values in a category column) — auto-pivoted when needed.
        z_key: Column for numeric Z values (heatmap only)
        stacked: When True and chart_type='bar', renders as stacked bar instead of grouped

    Examples:
        # Single-series line
        create_chart_from_sql(data_source_id=2, chart_type="line",
            sql_query="SELECT month, SUM(sales) as total FROM orders GROUP BY month ORDER BY month",
            x_key="month", y_key="total", title="Monthly Sales")

        # Multi-series line — use series_key (PREFERRED: simplest, works with long-format SQL)
        create_chart_from_sql(data_source_id=2, chart_type="line",
            sql_query="SELECT month, product, SUM(sales) as total FROM orders GROUP BY month, product",
            x_key="month", y_key="total", series_key="product", title="Sales by Product")

        # Multi-series bar (grouped)
        create_chart_from_sql(data_source_id=2, chart_type="bar",
            sql_query="SELECT date, platform, COUNT(*) as cnt FROM t GROUP BY date, platform",
            x_key="date", y_key="cnt", series_key="platform", title="Daily Active Users")

        # Stacked bar
        create_chart_from_sql(data_source_id=2, chart_type="bar", stacked=True,
            sql_query="SELECT date, platform, COUNT(*) as cnt FROM t GROUP BY date, platform",
            x_key="date", y_key="cnt", series_key="platform", title="Stacked Platform Usage")

        # Multi-series area
        create_chart_from_sql(data_source_id=2, chart_type="area",
            sql_query="SELECT month, product, SUM(sales) as total FROM orders GROUP BY month, product",
            x_key="month", y_key="total", series_key="product", title="Sales Area Chart")

        # Scatter colored by category
        create_chart_from_sql(data_source_id=2, chart_type="scatter",
            sql_query="SELECT price, quantity, category FROM products",
            x_key="price", y_key="quantity", series_key="category", title="Price vs Quantity")

        # Heatmap
        create_chart_from_sql(data_source_id=2, chart_type="heatmap",
            sql_query="SELECT month, product, SUM(sales) as total FROM sales GROUP BY month, product",
            x_key="month", y_key="product", z_key="total", title="Sales Heatmap")
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    user_id = runtime.user.user_id
    user_role = runtime.user.role
    profile = runtime.capability_profile
    if (
        profile
        and profile.allowed_data_source_ids is not None
        and data_source_id not in profile.allowed_data_source_ids
    ):
        return ToolResult.error_result("Data source is not assigned to this agent", code="PERMISSION_DENIED")

    logger.info(f"Creating chart from SQL: {title}, query: {sql_query[:80]}...")

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
                    user_id=user_id,
                    user_role=user_role,
                ),
                delegated_ids=delegated_data_source_ids(profile),
            )

            if df.empty:
                return ToolResult.error_result(
                    code="CHART_SQL_EMPTY_RESULT",
                    message=f"Query returned no data for chart '{title}'",
                )

            if len(df) > 500:
                logger.warning(f"Query returned {len(df)} rows, truncating to 500 for chart")
                df = df.head(500)

            data_list = df.to_dict(orient="records")
            data_json = json.dumps(data_list, ensure_ascii=False, default=str)

            result = render_chart(
                chart_type=chart_type,
                data=data_json,
                title=title,
                x_label=x_label,
                y_label=y_label,
                x_key=x_key,
                y_key=y_key,
                series_key=series_key,
                series_keys=series_keys,
                z_key=z_key,
                stacked=stacked,
            )

            logger.info(f"Chart created from SQL: {title} ({len(df)} data points)")
            return ToolResult.success({"markdown": result})

    except Exception as e:
        error_msg = f"Error creating chart from SQL: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return ToolResult.error_result(
            code="CHART_CREATE_FROM_SQL_FAILED",
            message=error_msg,
        )
