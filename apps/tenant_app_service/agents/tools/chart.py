"""Chart tool wrappers for agents.

Rendering logic lives in apps.shared.chart.renderer.  These tools wire LangGraph
inputs to render_chart() and ChartService artifact registration.
"""

from typing import List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.chart.renderer import render_chart
from apps.shared.chart.types import AgentChartInputType
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.chart_support import (
    assert_data_source_allowed,
    chart_render_kwargs,
    chart_tool_success,
    exception_detail,
    is_sql_empty_result,
    query_sql_as_json_records,
    register_agent_chart,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


@tool
async def create_chart_from_structured_data(
    chart_type: AgentChartInputType,
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
    subtitle: str | None = None,
    reference_lines_json: str | None = None,
    annotations_json: str | None = None,
    y_axis_percent: bool = False,
    measure_key: str | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Create an axis-style chart (SVG) using Plotly from structured data.

    Args:
        chart_type: 'bar', 'horizontal_bar', 'line', 'pie', 'scatter', 'area', 'heatmap', 'waterfall', 'box', or 'violin'.
            Use series_key or series_keys for multi-series bar, line, or area.
        data: JSON array of objects, e.g. '[{"month":"Jan","sales":100}, ...]'
        title: Chart title
        x_key: Column for the X-axis (defaults to the first column if omitted)
        y_key: Column for values (single-series); for heatmap, the row dimension column
        x_label: X-axis label (defaults to x_key)
        y_label: Y-axis label (defaults to y_key; set explicitly for multi-series charts)
        series_key: Column whose values identify the series on each row (pairs with y_key)
        series_keys: List of columns, each holding one series (e.g. ["region_a", "region_b"])
        z_key: Value column for heatmap intensity
        stacked: With chart_type='bar' and multiple series, stack bars instead of grouping
        subtitle: Optional subtitle under the chart title
        reference_lines_json: JSON array of {y, label?} horizontal reference lines
        annotations_json: JSON array of {x, y, text} callout annotations
        y_axis_percent: Format Y axis as percent when values are rates
        measure_key: Waterfall only — column with relative|absolute|total measure types
        config: Runtime configuration (auto-injected by LangGraph)

    Returns:
        ToolResult with ``markdown`` containing a persisted chart image URL (``/charts/{id}/image.svg``).

    Examples:
        # Bar — one metric by category
        create_chart_from_structured_data(
            chart_type="bar",
            data='[{"month":"Jan","sales":100},{"month":"Feb","sales":120}]',
            title="Monthly Sales",
            x_key="month",
            y_key="sales",
            x_label="Month",
            y_label="Sales",
        )

        # Line — one metric over time
        create_chart_from_structured_data(
            chart_type="line",
            data='[{"week":"2026-W01","revenue":900},{"week":"2026-W02","revenue":1100}]',
            title="Weekly Revenue",
            x_key="week",
            y_key="revenue",
            y_label="Revenue",
        )

        # Pie — share by category (x_key = slice label, y_key = value)
        create_chart_from_structured_data(
            chart_type="pie",
            data='[{"channel":"Web","orders":40},{"channel":"Retail","orders":25}]',
            title="Orders by Channel",
            x_key="channel",
            y_key="orders",
        )

        # Multi-series bar — series name on each row (series_key + shared value column)
        create_chart_from_structured_data(
            chart_type="bar",
            data='[{"month":"Jan","product":"A","sales":100},{"month":"Jan","product":"B","sales":80}]',
            title="Sales by Product",
            x_key="month",
            y_key="sales",
            series_key="product",
            y_label="Sales",
        )

        # Multi-series line — one column per series (series_keys)
        create_chart_from_structured_data(
            chart_type="line",
            data='[{"date":"2026-09-01","current":100,"prior":90},{"date":"2026-09-02","current":110,"prior":95}]',
            title="Current vs Prior Period",
            x_key="date",
            series_keys=["current", "prior"],
            x_label="Date",
            y_label="Amount",
        )

        # Stacked bar — same data shape as multi-series bar, with stacked=True
        create_chart_from_structured_data(
            chart_type="bar",
            stacked=True,
            data='[{"month":"Jan","product":"A","sales":100},{"month":"Jan","product":"B","sales":80}]',
            title="Stacked Sales",
            x_key="month",
            y_key="sales",
            series_key="product",
            y_label="Sales",
        )

        # Area — multi-series (series_key)
        create_chart_from_structured_data(
            chart_type="area",
            data='[{"month":"Jan","segment":"X","total":50},{"month":"Feb","segment":"X","total":60}]',
            title="Segment Trend",
            x_key="month",
            y_key="total",
            series_key="segment",
            y_label="Total",
        )

        # Scatter — points colored by category (series_key)
        create_chart_from_structured_data(
            chart_type="scatter",
            data='[{"price":10,"qty":5,"cat":"A"},{"price":20,"qty":8,"cat":"B"}]',
            title="Price vs Quantity",
            x_key="price",
            y_key="qty",
            series_key="cat",
            x_label="Price",
            y_label="Quantity",
        )

        # Heatmap — x and y are grid dimensions, z_key is the cell value
        create_chart_from_structured_data(
            chart_type="heatmap",
            data='[{"product":"A","month":"Jan","sales":100},{"product":"B","month":"Jan","sales":80}]',
            title="Sales Heatmap",
            x_key="month",
            y_key="product",
            z_key="sales",
        )
    """
    logger.info(f"Creating static Plotly chart: type={chart_type}, title={title}")
    try:
        runtime = extract_runtime_context(config)
        rendered = render_chart(
            **chart_render_kwargs(
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
                subtitle=subtitle,
                reference_lines_json=reference_lines_json,
                annotations_json=annotations_json,
                y_axis_percent=y_axis_percent,
                measure_key=measure_key,
            )
        )
        markdown = await register_agent_chart(rendered=rendered, runtime=runtime)
        logger.info(f"Static chart created: {title}")
        return chart_tool_success(markdown)

    except ValueError as e:
        logger.warning("Structured chart tool failed (validation/context): %s", e)
        return ToolResult.error_result(
            code="CHART_RUNTIME_CONTEXT_REQUIRED",
            message=str(e),
        )
    except Exception as e:
        detail = exception_detail(e)
        logger.error("Error creating static Plotly chart: %s", detail, exc_info=True)
        return ToolResult.error_result(
            code="CHART_CREATE_FROM_STRUCTURED_DATA_FAILED",
            message=f"Error creating chart: {detail}",
        )


@tool
async def create_chart_from_sql(
    data_source_id: int,
    sql_query: str,
    chart_type: AgentChartInputType,
    x_key: str,
    title: str,
    y_key: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    series_key: str | None = None,
    series_keys: List[str] | None = None,
    z_key: str | None = None,
    stacked: bool = False,
    subtitle: str | None = None,
    reference_lines_json: str | None = None,
    annotations_json: str | None = None,
    y_axis_percent: bool = False,
    measure_key: str | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Create an axis-style chart from SQL query results.

    Args:
        data_source_id: Data source ID
        sql_query: SQL SELECT query (≤100 rows recommended for readability)
        chart_type: 'bar', 'horizontal_bar', 'line', 'pie', 'scatter', 'area', 'heatmap', 'waterfall', 'box', or 'violin'
        title: Chart title
        x_key: Result column for the X-axis (or slice labels for pie)
        y_key: Result column for values (single-series); row labels for heatmap y-axis
        x_label: X-axis label (defaults to x_key)
        y_label: Y-axis label (defaults to y_key; set explicitly for multi-series charts)
        series_key: Result column that names the series on each row, with y_key as the value column
        series_keys: Result columns where each column is one series (omit series_key)
        z_key: Result column for heatmap cell values
        stacked: With chart_type='bar' and multiple series, stack bars instead of grouping
        subtitle: Optional subtitle under the chart title
        reference_lines_json: JSON array of {y, label?} horizontal reference lines
        annotations_json: JSON array of {x, y, text} callout annotations
        y_axis_percent: Format Y axis as percent when values are rates
        measure_key: Waterfall only — column with relative|absolute|total measure types
        config: Runtime configuration (auto-injected by LangGraph)

    Returns:
        ToolResult with ``markdown`` containing a persisted chart image URL (``/charts/{id}/image.svg``).

    Examples:
        # Line — one metric
        create_chart_from_sql(
            data_source_id=2,
            chart_type="line",
            sql_query="SELECT month, SUM(sales) AS total FROM orders GROUP BY month ORDER BY month",
            title="Monthly Sales",
            x_key="month",
            y_key="total",
            x_label="Month",
            y_label="Sales",
        )

        # Bar — one metric
        create_chart_from_sql(
            data_source_id=2,
            chart_type="bar",
            sql_query="SELECT region, SUM(revenue) AS revenue FROM sales GROUP BY region",
            title="Revenue by Region",
            x_key="region",
            y_key="revenue",
            y_label="Revenue",
        )

        # Pie — label and value columns
        create_chart_from_sql(
            data_source_id=2,
            chart_type="pie",
            sql_query="SELECT category, COUNT(*) AS cnt FROM tickets GROUP BY category",
            title="Tickets by Category",
            x_key="category",
            y_key="cnt",
        )

        # Multi-series line — one row per (x, series) with series_key
        create_chart_from_sql(
            data_source_id=2,
            chart_type="line",
            sql_query=(
                "SELECT month, product, SUM(sales) AS total "
                "FROM orders GROUP BY month, product ORDER BY month, product"
            ),
            title="Sales by Product",
            x_key="month",
            y_key="total",
            series_key="product",
            y_label="Sales",
        )

        # Multi-series line — one column per series (series_keys)
        create_chart_from_sql(
            data_source_id=2,
            chart_type="line",
            sql_query=(
                "SELECT dt, SUM(CASE WHEN yr=2026 THEN amt END) AS current_yr, "
                "SUM(CASE WHEN yr=2025 THEN amt END) AS prior_yr "
                "FROM daily GROUP BY dt ORDER BY dt"
            ),
            title="Current vs Prior Year",
            x_key="dt",
            series_keys=["current_yr", "prior_yr"],
            x_label="Date",
            y_label="Amount",
        )

        # Grouped bar — series_key
        create_chart_from_sql(
            data_source_id=2,
            chart_type="bar",
            sql_query="SELECT day, platform, COUNT(*) AS cnt FROM events GROUP BY day, platform",
            title="Events by Platform",
            x_key="day",
            y_key="cnt",
            series_key="platform",
            y_label="Count",
        )

        # Stacked bar — same SQL shape as grouped bar, stacked=True
        create_chart_from_sql(
            data_source_id=2,
            chart_type="bar",
            stacked=True,
            sql_query="SELECT day, platform, COUNT(*) AS cnt FROM events GROUP BY day, platform",
            title="Stacked Events by Platform",
            x_key="day",
            y_key="cnt",
            series_key="platform",
            y_label="Count",
        )

        # Area — multi-series
        create_chart_from_sql(
            data_source_id=2,
            chart_type="area",
            sql_query="SELECT week, segment, SUM(amount) AS total FROM revenue GROUP BY week, segment",
            title="Revenue by Segment",
            x_key="week",
            y_key="total",
            series_key="segment",
            y_label="Amount",
        )

        # Scatter — color by category
        create_chart_from_sql(
            data_source_id=2,
            chart_type="scatter",
            sql_query="SELECT price, quantity, category FROM products LIMIT 200",
            title="Price vs Quantity",
            x_key="price",
            y_key="quantity",
            series_key="category",
            x_label="Price",
            y_label="Quantity",
        )

        # Heatmap
        create_chart_from_sql(
            data_source_id=2,
            chart_type="heatmap",
            sql_query="SELECT month, product, SUM(sales) AS total FROM sales GROUP BY month, product",
            title="Sales Heatmap",
            x_key="month",
            y_key="product",
            z_key="total",
        )
    """
    runtime = extract_runtime_context(config)
    denied = assert_data_source_allowed(runtime=runtime, data_source_id=data_source_id)
    if denied is not None:
        return denied

    logger.info(f"Creating chart from SQL: {title}, query: {sql_query[:80]}...")

    data_json, err = await query_sql_as_json_records(
        runtime=runtime,
        data_source_id=data_source_id,
        sql_query=sql_query,
    )
    if err is not None:
        if is_sql_empty_result(err):
            return ToolResult.error_result(
                code="CHART_SQL_EMPTY_RESULT",
                message=f"Query returned no data for chart '{title}'",
            )
        return err

    try:
        rendered = render_chart(
            **chart_render_kwargs(
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
                subtitle=subtitle,
                reference_lines_json=reference_lines_json,
                annotations_json=annotations_json,
                y_axis_percent=y_axis_percent,
                measure_key=measure_key,
            )
        )
        markdown = await register_agent_chart(rendered=rendered, runtime=runtime)
        logger.info(f"Chart created from SQL: {title}")
        return chart_tool_success(markdown)
    except Exception as e:
        detail = exception_detail(e)
        error_msg = f"Error creating chart from SQL: {detail}"
        logger.error(error_msg, exc_info=True)
        return ToolResult.error_result(
            code="CHART_CREATE_FROM_SQL_FAILED",
            message=error_msg,
            hint="Check SQL syntax, column names, and data-source permissions. Fix the query and retry.",
        )
