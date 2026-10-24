"""Multi-panel (small-multiples) report charts in one figure."""

from __future__ import annotations

import json
from typing import Any, cast

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from apps.shared.chart.data_processor import ensure_numeric_series
from apps.shared.chart.enhancements import apply_chart_enhancements
from apps.shared.chart.renderer import _plotly_figure_to_result
from apps.shared.chart.types import GRID_PANEL_CHART_TYPES, ChartRenderResult, GridPanelChartType


def _panel_chart_type(raw: str) -> GridPanelChartType:
    if raw not in GRID_PANEL_CHART_TYPES:
        raise ValueError(
            f"Panel chart_type '{raw}' is not supported in grid (use bar, horizontal_bar, line, or pie)."
        )
    return cast(GridPanelChartType, raw)


def _panel_trace(
    chart_type: GridPanelChartType,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> go.BaseTraceType:
    x_vals = [row[x_key] for row in rows]
    y_vals = ensure_numeric_series([row[y_key] for row in rows], chart_type, field_name=y_key)

    if chart_type == "horizontal_bar":
        return go.Bar(x=y_vals, y=x_vals, orientation="h", marker=dict(color="#667eea"))
    if chart_type == "bar":
        return go.Bar(x=x_vals, y=y_vals, marker=dict(color="#667eea"))
    if chart_type == "line":
        return go.Scatter(x=x_vals, y=y_vals, mode="lines+markers", line=dict(color="#667eea"))
    if chart_type == "pie":
        return go.Pie(labels=x_vals, values=y_vals, textinfo="label+percent")
    raise ValueError(f"Unhandled panel chart_type '{chart_type}'")


def render_chart_grid(
    *,
    data: str,
    title: str,
    panels: str,
    rows: int = 2,
    cols: int = 2,
    subtitle: str | None = None,
) -> ChartRenderResult:
    """Render up to rows×cols panels sharing one JSON data array."""
    data_list: list[dict[str, Any]] = json.loads(data)
    if not data_list:
        raise ValueError("No data provided for chart grid")

    panel_specs: list[dict[str, Any]] = json.loads(panels)
    if not panel_specs:
        raise ValueError("panels must be a non-empty JSON array")
    max_panels = rows * cols
    if len(panel_specs) > max_panels:
        raise ValueError(f"At most {max_panels} panels for a {rows}x{cols} grid")

    subplot_titles = [p.get("title") or "" for p in panel_specs]
    while len(subplot_titles) < max_panels:
        subplot_titles.append("")

    specs: list[list[dict[str, str]]] = [[{"type": "xy"} for _ in range(cols)] for _ in range(rows)]
    for panel in panel_specs:
        if str(panel.get("chart_type", "bar")) == "pie":
            row_i = int(panel.get("row") or 1) - 1
            col_i = int(panel.get("col") or 1) - 1
            specs[row_i][col_i] = {"type": "domain"}

    fig = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=subplot_titles[:max_panels],
        specs=specs,
        horizontal_spacing=0.08,
        vertical_spacing=0.12,
    )

    for panel in panel_specs:
        chart_type = _panel_chart_type(str(panel.get("chart_type", "bar")))
        x_key = panel.get("x_key")
        y_key = panel.get("y_key")
        if not x_key or not y_key:
            raise ValueError("Each panel requires x_key and y_key")
        row = int(panel.get("row") or 1)
        col = int(panel.get("col") or 1)
        trace = _panel_trace(chart_type, data_list, x_key, y_key)
        fig.add_trace(trace, row=row, col=col)

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0.5, xanchor="center"),
        template="plotly_white",
        paper_bgcolor="white",
        height=320 * rows,
        width=480 * cols,
        showlegend=False,
    )
    apply_chart_enhancements(
        fig,
        subtitle=subtitle,
        reference_lines=None,
        annotations=None,
        y_axis_percent=False,
        y_numeric_samples=None,
    )
    return _plotly_figure_to_result(fig, title)
