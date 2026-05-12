r"""Server-side Plotly SVG chart renderer.

Provides render_chart() — the single public entry point that converts
structured data into a persisted SVG file and returns a markdown image string.

Output format:  "\n\n![title](https://.../static/charts/chart_*.svg)\n\n"

SVG is used because:
- Vector quality at any resolution
- Smaller files than raster formats
- Embeds directly in markdown/HTML without a browser
- Works in PDF/Word export by reading the saved file (no re-rendering needed)
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import plotly.graph_objects as go

from apps.config import EnvConfig, get_charts_path
from apps.shared.chart.data_processor import (
    coerce_numeric_value,
    ensure_numeric_series,
    format_value_labels,
    handle_duplicate_x_values,
    pivot_long_to_wide,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def render_chart(
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
) -> str:
    r"""Render chart from JSON data and return a markdown image string.

    Args:
        chart_type: Public chart type. One of: 'bar', 'line', 'pie', 'scatter',
            'area', 'heatmap'. Add series_key/series_keys for multi-series variants.
            Internal types 'grouped_bar', 'stacked_bar', 'multi_line', 'multi_area'
            are accepted for backwards compatibility.
        data: JSON string of a list of dicts, e.g. '[{"month":"Jan","val":10}, ...]'
        title: Chart title (also used as SVG filename fragment).
        x_label: X-axis label (defaults to x_key).
        y_label: Y-axis label (defaults to y_key or first series name).
        x_key: Column for X-axis values.
        y_key: Column for Y values (single-series) or value column for multi-series pivot.
        series_key: Single column name whose distinct values define the series (long format).
        series_keys: Explicit list of series column names (wide/long format).
        z_key: Column for Z values (heatmap only).
        stacked: When True with chart_type='bar', renders stacked instead of grouped.

    Returns:
        Markdown image string: "\\n\\n![title](url)\\n\\n"
    """
    data_list: List[Dict[str, Any]] = json.loads(data)
    if not data_list:
        return "Error: No data provided for visualization"

    # Resolve series_key (single column name) into series_keys (list of distinct values).
    # series_key is the preferred API for long-format data; series_keys is the advanced form.
    if series_key and not series_keys:
        if series_key not in data_list[0]:
            columns = sorted(data_list[0].keys())
            raise ValueError(
                f"series_key='{series_key}' not found in data columns: {columns}. Check the column name spelling."
            )
        # Scatter with series_key uses categorical coloring, not a pivot.
        if chart_type == "scatter":
            return _render_scatter_categorical(
                data_list, x_key, y_key, series_key, x_label, y_label, title, "plotly_white"
            )
        # All other types: extract distinct values in order of first appearance.
        seen: dict = {}
        for row in data_list:
            v = str(row[series_key])
            if v not in seen:
                seen[v] = True
        series_keys = list(seen.keys())

    internal_chart_type = _normalize_chart_type(chart_type, series_keys, stacked)

    if internal_chart_type not in ["grouped_bar", "stacked_bar", "multi_line", "multi_area", "heatmap"]:
        if not x_key or not y_key:
            keys = list(data_list[0].keys())
            x_key = x_key or keys[0]
            y_key = y_key or (keys[1] if len(keys) > 1 else keys[0])

        _validate_data_keys(data_list, internal_chart_type, x_key, y_key, None, None)

        x_values = [row[x_key] for row in data_list]
        y_values = [row[y_key] for row in data_list]

        if internal_chart_type in ["bar", "line", "area", "pie", "scatter"]:
            y_values = ensure_numeric_series(y_values, internal_chart_type, field_name=y_key)

        x_values = handle_duplicate_x_values(x_values)

        resolved_x_label = x_label or x_key
        resolved_y_label = y_label or y_key
        series_data = None
    else:
        if internal_chart_type == "heatmap":
            _validate_data_keys(data_list, internal_chart_type, x_key, y_key, None, z_key)
        else:
            if series_keys:
                data_list = pivot_long_to_wide(data_list, x_key, series_keys, value_col=y_key)
            _validate_data_keys(data_list, internal_chart_type, x_key, None, series_keys, None)

        x_values = None
        y_values = None
        resolved_x_label = x_label or x_key or ""
        resolved_y_label = y_label or (series_keys[0] if series_keys else y_key or "")
        series_data = {
            "data_list": data_list,
            "x_key": x_key,
            "y_key": y_key,
            "series_keys": series_keys,
            "z_key": z_key,
        }

    fig = _create_plotly_figure(
        internal_chart_type,
        x_values,
        y_values,
        resolved_x_label,
        resolved_y_label,
        title,
        "plotly_white",
        series_data,
    )
    chart_url = _save_plotly_chart(fig, title)
    return f"\n\n![{title}]({chart_url})\n\n"


# ---------------------------------------------------------------------------
# Internal helpers — not part of the public API
# ---------------------------------------------------------------------------


def _normalize_chart_type(
    chart_type: str,
    series_keys: List[str] | None,
    stacked: bool,
) -> str:
    """Map public chart_type names to internal renderer types."""
    _valid_types = {
        "bar",
        "line",
        "pie",
        "scatter",
        "area",
        "heatmap",
        "grouped_bar",
        "stacked_bar",
        "multi_line",
        "multi_area",
    }
    if chart_type not in _valid_types:
        raise ValueError(
            f"Unknown chart_type '{chart_type}'. "
            f"Valid types: 'bar', 'line', 'pie', 'scatter', 'area', 'heatmap'. "
            f"For multi-series bar/line/area, use the type and provide series_key or series_keys."
        )
    if chart_type == "bar" and series_keys:
        return "stacked_bar" if stacked else "grouped_bar"
    if chart_type == "line" and series_keys:
        return "multi_line"
    if chart_type == "area" and series_keys:
        return "multi_area"
    return chart_type


def _validate_data_keys(
    data_list: List[Dict[str, Any]],
    chart_type: str,
    x_key: str | None,
    y_key: str | None,
    series_keys: List[str] | None,
    z_key: str | None,
) -> None:
    """Validate that all referenced column keys exist in the data."""
    columns = set(data_list[0].keys())

    def _check(key: str, param: str) -> None:
        if key and key not in columns:
            raise ValueError(
                f"{param}='{key}' not found in data columns: {sorted(columns)}. Check the column name spelling."
            )

    _check(x_key, "x_key")
    _check(y_key, "y_key")
    _check(z_key, "z_key")

    if chart_type == "heatmap":
        if not y_key:
            raise ValueError("heatmap requires y_key (the row-label column).")
        if not z_key:
            raise ValueError(f"heatmap requires z_key (the numeric value column). Available columns: {sorted(columns)}")

    if chart_type in ("grouped_bar", "stacked_bar", "multi_line", "multi_area"):
        if not series_keys:
            raise ValueError(f"chart_type='{chart_type}' requires series_keys. Available columns: {sorted(columns)}")
        missing = [sk for sk in series_keys if sk not in columns]
        if missing:
            raise ValueError(
                f"series_keys {missing} not found in data columns after pivot: {sorted(columns)}. "
                f"Verify series_keys match column names (wide format) or values in a category column "
                f"(long format)."
            )


def _generate_colors(n: int, palette: str = "gradient") -> List[str]:
    """Generate n distinct colors from a named palette."""
    palettes = {
        "gradient": [
            "#667eea",
            "#764ba2",
            "#f093fb",
            "#4facfe",
            "#fa709a",
            "#fee140",
            "#30cfd0",
            "#330867",
            "#a8edea",
            "#fed6e3",
            "#ff6a88",
            "#fcb69f",
            "#ffecd2",
            "#a1c4fd",
            "#c2e9fb",
            "#fccb90",
            "#d57eeb",
            "#ffc3a0",
            "#92fe9d",
            "#00c9ff",
        ],
        "vibrant": [
            "#11998e",
            "#38ef7d",
            "#fa709a",
            "#fee140",
            "#667eea",
            "#764ba2",
            "#f093fb",
            "#4facfe",
            "#ff6a88",
            "#fcb69f",
            "#30cfd0",
            "#330867",
            "#a8edea",
            "#fed6e3",
            "#ffecd2",
            "#a1c4fd",
            "#c2e9fb",
            "#fccb90",
            "#d57eeb",
            "#ffc3a0",
        ],
    }
    base_colors = palettes.get(palette, palettes["gradient"])
    if n <= len(base_colors):
        return base_colors[:n]
    return [base_colors[i % len(base_colors)] for i in range(n)]


def _save_plotly_chart(fig: go.Figure, title: str) -> str:
    """Save Plotly figure as SVG and return its public URL."""
    chart_id = str(uuid.uuid4())[:8]
    timestamp = int(time.time())
    safe_title = "".join(c if c.isalnum() else "_" for c in title)[:30]
    static_dir = Path(get_charts_path())
    filename = f"chart_{timestamp}_{safe_title}_{chart_id}.svg"
    file_path = static_dir / filename

    # Use fig.to_image() which works with kaleido for SVG export

    svg_bytes = fig.to_image(format="svg", scale=1)
    file_path.write_bytes(svg_bytes)

    file_size = file_path.stat().st_size
    logger.info(f"Plotly chart saved: {file_path} (size: {file_size / 1024:.1f} KB)")

    api_base = EnvConfig.CHART_SERVICE_URL.rstrip("/")
    return f"{api_base}/static/charts/{filename}"


def _create_plotly_figure(
    chart_type: str,
    x_values: List[Any] | None,
    y_values: List[Any] | None,
    x_label: str,
    y_label: str,
    title: str,
    theme: str,
    series_data: Dict[str, Any] | None = None,
) -> go.Figure:
    """Route to the correct figure builder based on chart type."""
    if chart_type in ["grouped_bar", "stacked_bar", "multi_line"]:
        return _create_multi_series_figure(chart_type, x_label, y_label, title, theme, series_data)
    elif chart_type == "multi_area":
        return _create_multi_area_figure(x_label, y_label, title, theme, series_data)
    elif chart_type == "heatmap":
        return _create_heatmap_figure(x_label, y_label, title, theme, series_data)
    else:
        return _create_single_series_figure(chart_type, x_values, y_values, x_label, y_label, title, theme)


def _create_single_series_figure(
    chart_type: str,
    x_values: List[Any],
    y_values: List[Any],
    x_label: str,
    y_label: str,
    title: str,
    theme: str,
) -> go.Figure:
    """Create single-series charts: bar, line, area, pie, scatter."""
    num_points = len(y_values)
    colors_gradient = _generate_colors(num_points, "gradient")
    colors_vibrant = _generate_colors(num_points, "vibrant")

    if chart_type == "bar":
        bar_colors = colors_gradient[0] if num_points == 1 else colors_gradient
        fig = go.Figure(
            data=[
                go.Bar(
                    x=x_values,
                    y=y_values,
                    marker=dict(color=bar_colors, line=dict(color="rgba(0,0,0,0.1)", width=1.5)),
                    text=format_value_labels(y_values),
                    textposition="outside",
                    textfont=dict(size=11, color="#2c3e50"),
                    cliponaxis=False,
                    hovertemplate=(f"<b>%{{x}}</b><br>{y_label}: %{{y:,.2f}}<br><extra></extra>"),
                )
            ]
        )

    elif chart_type == "line":
        fig = go.Figure(
            data=[
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    mode="lines+markers+text",
                    line=dict(color="#667eea", width=3, shape="spline"),
                    marker=dict(size=10, color="#667eea", line=dict(color="white", width=2), symbol="circle"),
                    text=format_value_labels(y_values),
                    textposition="top center",
                    textfont=dict(size=10, color="#2c3e50"),
                    cliponaxis=False,
                    hovertemplate=(f"<b>%{{x}}</b><br>{y_label}: %{{y:,.2f}}<br><extra></extra>"),
                )
            ]
        )

    elif chart_type == "area":
        fig = go.Figure(
            data=[
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    fill="tozeroy",
                    mode="lines+markers",
                    line=dict(color="#11998e", width=2, shape="spline"),
                    fillcolor="rgba(17, 153, 142, 0.2)",
                    marker=dict(size=8, color="#11998e", line=dict(color="white", width=2)),
                    hovertemplate=(f"<b>%{{x}}</b><br>{y_label}: %{{y:,.2f}}<br><extra></extra>"),
                )
            ]
        )

    elif chart_type == "pie":
        total = sum(y_values)
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=x_values,
                    values=y_values,
                    marker=dict(colors=colors_vibrant, line=dict(color="white", width=2)),
                    textinfo="label+percent",
                    textfont=dict(size=12, color="white"),
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        f"{y_label}: %{{value:,.0f}}<br>"
                        "Percentage: %{percent}<br>"
                        "<extra></extra>"
                    ),
                    hole=0.3,
                    pull=[0.05 if i == y_values.index(max(y_values)) else 0 for i in range(len(y_values))],
                )
            ]
        )
        fig.add_annotation(
            text=f"Total<br>{total:,.0f}",
            x=0.5,
            y=0.5,
            font=dict(size=16, color="#2c3e50"),
            showarrow=False,
        )

    elif chart_type == "scatter":
        fig = go.Figure(
            data=[
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    mode="markers",
                    marker=dict(
                        size=14,
                        color=y_values,
                        colorscale="Plasma",
                        showscale=True,
                        colorbar=dict(title=dict(text=y_label, side="right"), thickness=15, len=0.7),
                        line=dict(color="white", width=1),
                        opacity=0.8,
                    ),
                    text=format_value_labels(y_values),
                    hovertemplate=(f"<b>{x_label}: %{{x}}</b><br>{y_label}: %{{y:,.2f}}<br><extra></extra>"),
                )
            ]
        )

    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=22, color="#2c3e50", family="Arial, sans-serif"),
            x=0.5,
            xanchor="center",
        ),
        xaxis=dict(
            title=dict(text=f"<b>{x_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            linecolor="rgba(200, 200, 200, 0.5)",
            linewidth=1,
            mirror=True,
            tickfont=dict(size=11),
            tickangle=-45 if chart_type in ["bar", "line"] and len(x_values) > 6 else 0,
            automargin=True,
        ),
        yaxis=dict(
            title=dict(text=f"<b>{y_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            linecolor="rgba(200, 200, 200, 0.5)",
            linewidth=1,
            mirror=True,
            tickfont=dict(size=11),
            zeroline=True,
            zerolinecolor="rgba(200, 200, 200, 0.3)",
            automargin=True,
        ),
        template=theme,
        hovermode="closest",
        showlegend=False,
        plot_bgcolor="rgba(250, 250, 250, 0.5)",
        paper_bgcolor="white",
        margin=dict(l=90, r=90, t=120, b=120),
        height=600,
        font=dict(family="Arial, sans-serif", size=12, color="#2c3e50"),
        hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial, sans-serif", bordercolor="#667eea"),
    )
    return fig


def _create_multi_series_figure(
    chart_type: str,
    x_label: str,
    y_label: str,
    title: str,
    theme: str,
    series_data: Dict[str, Any],
) -> go.Figure:
    """Create grouped bar, stacked bar, or multi-line chart."""
    data_list = series_data["data_list"]
    x_key = series_data["x_key"]
    series_keys = series_data["series_keys"]

    if not series_keys:
        raise ValueError(f"{chart_type} requires series_keys parameter")

    x_values = [row[x_key] for row in data_list]
    colors = _generate_colors(len(series_keys), "vibrant")
    fig = go.Figure()

    for idx, series_key in enumerate(series_keys):
        y_values = [row.get(series_key, 0) for row in data_list]
        y_values = ensure_numeric_series(y_values, chart_type, field_name=series_key)

        if chart_type == "grouped_bar":
            fig.add_trace(
                go.Bar(
                    name=series_key,
                    x=x_values,
                    y=y_values,
                    marker=dict(color=colors[idx], line=dict(color="rgba(0,0,0,0.1)", width=1)),
                    text=format_value_labels(y_values),
                    textposition="outside",
                    hovertemplate=f"<b>{series_key}</b><br>%{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
                )
            )
        elif chart_type == "stacked_bar":
            fig.add_trace(
                go.Bar(
                    name=series_key,
                    x=x_values,
                    y=y_values,
                    marker=dict(color=colors[idx]),
                    hovertemplate=f"<b>{series_key}</b><br>%{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
                )
            )
        elif chart_type == "multi_line":
            fig.add_trace(
                go.Scatter(
                    name=series_key,
                    x=x_values,
                    y=y_values,
                    mode="lines+markers",
                    line=dict(color=colors[idx], width=2.5),
                    marker=dict(size=8, color=colors[idx], line=dict(color="white", width=1.5)),
                    hovertemplate=f"<b>{series_key}</b><br>%{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
                )
            )

    if chart_type == "stacked_bar":
        fig.update_layout(barmode="stack")
    elif chart_type == "grouped_bar":
        fig.update_layout(barmode="group")

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=22, color="#2c3e50"), x=0.5, xanchor="center"),
        xaxis=dict(
            title=dict(text=f"<b>{x_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            tickangle=-45 if len(x_values) > 6 else 0,
        ),
        yaxis=dict(
            title=dict(text=f"<b>{y_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
        ),
        template=theme,
        hovermode="closest",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=40, t=120, b=100),
        height=600,
    )
    return fig


def _create_multi_area_figure(
    x_label: str,
    y_label: str,
    title: str,
    theme: str,
    series_data: Dict[str, Any],
) -> go.Figure:
    """Create multi-series area chart with semi-transparent overlapping fills."""
    data_list = series_data["data_list"]
    x_key = series_data["x_key"]
    series_keys = series_data["series_keys"]

    if not series_keys:
        raise ValueError("multi_area requires series_keys parameter")

    x_values = [row[x_key] for row in data_list]
    colors = _generate_colors(len(series_keys), "vibrant")

    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    fig = go.Figure()
    for idx, series_key in enumerate(series_keys):
        y_values = [row.get(series_key, 0) for row in data_list]
        y_values = ensure_numeric_series(y_values, "multi_area", field_name=series_key)
        color = colors[idx]
        fig.add_trace(
            go.Scatter(
                name=series_key,
                x=x_values,
                y=y_values,
                mode="lines",
                fill="tozeroy",
                line=dict(color=color, width=2, shape="spline"),
                fillcolor=_hex_to_rgba(color, 0.18),
                hovertemplate=f"<b>{series_key}</b><br>%{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=22, color="#2c3e50"), x=0.5, xanchor="center"),
        xaxis=dict(
            title=dict(text=f"<b>{x_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            tickangle=-45 if len(x_values) > 6 else 0,
            automargin=True,
        ),
        yaxis=dict(
            title=dict(text=f"<b>{y_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            automargin=True,
        ),
        template=theme,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=40, t=120, b=100),
        height=600,
    )
    return fig


def _create_heatmap_figure(
    x_label: str,
    y_label: str,
    title: str,
    theme: str,
    series_data: Dict[str, Any],
) -> go.Figure:
    """Create heatmap from data."""
    data_list = series_data["data_list"]
    x_key = series_data["x_key"]
    y_key = series_data["y_key"]
    z_key = series_data.get("z_key", "value")

    x_values = sorted(list(set(row[x_key] for row in data_list)))
    y_values = sorted(list(set(row[y_key] for row in data_list)))
    z_matrix = [[0] * len(x_values) for _ in range(len(y_values))]

    for row in data_list:
        x_idx = x_values.index(row[x_key])
        y_idx = y_values.index(row[y_key])
        numeric_z = coerce_numeric_value(row.get(z_key, 0))
        z_matrix[y_idx][x_idx] = numeric_z if numeric_z is not None else 0

    fig = go.Figure(
        data=go.Heatmap(
            z=z_matrix,
            x=x_values,
            y=y_values,
            colorscale="RdYlGn",
            text=[[f"{val:,.0f}" for val in row] for row in z_matrix],
            texttemplate="%{text}",
            textfont={"size": 12},
            hovertemplate=f"<b>{x_label}: %{{x}}</b><br>{y_label}: %{{y}}<br>Value: %{{z:,.2f}}<extra></extra>",
            colorbar=dict(title="Value", thickness=15, len=0.7),
        )
    )
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=22, color="#2c3e50"), x=0.5, xanchor="center"),
        xaxis=dict(title=dict(text=f"<b>{x_label}</b>", font=dict(size=14)), side="bottom"),
        yaxis=dict(title=dict(text=f"<b>{y_label}</b>", font=dict(size=14))),
        template=theme,
        margin=dict(l=100, r=100, t=100, b=100),
        height=600,
    )
    return fig


def _render_scatter_categorical(
    data_list: List[Dict[str, Any]],
    x_key: str | None,
    y_key: str | None,
    series_key: str,
    x_label: str | None,
    y_label: str | None,
    title: str,
    theme: str,
) -> str:
    """Render scatter chart with marker color per category (series_key column)."""
    if not x_key or not y_key:
        keys = list(data_list[0].keys())
        x_key = x_key or keys[0]
        y_key = y_key or (keys[1] if len(keys) > 1 else keys[0])

    resolved_x_label = x_label or x_key
    resolved_y_label = y_label or y_key

    categories: Dict[str, List] = {}
    cat_order: List[str] = []
    for row in data_list:
        cat = str(row.get(series_key, ""))
        if cat not in categories:
            categories[cat] = []
            cat_order.append(cat)
        categories[cat].append(row)

    colors = _generate_colors(len(cat_order), "vibrant")
    fig = go.Figure()

    for idx, cat in enumerate(cat_order):
        rows = categories[cat]
        x_vals = [row[x_key] for row in rows]
        y_vals = ensure_numeric_series([row[y_key] for row in rows], "scatter", field_name=y_key)
        color = colors[idx]
        fig.add_trace(
            go.Scatter(
                name=cat,
                x=x_vals,
                y=y_vals,
                mode="markers",
                marker=dict(size=10, color=color, opacity=0.8, line=dict(color="white", width=1)),
                hovertemplate=(
                    f"<b>{cat}</b><br>{resolved_x_label}: %{{x}}<br>{resolved_y_label}: %{{y:,.2f}}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=22, color="#2c3e50"), x=0.5, xanchor="center"),
        xaxis=dict(
            title=dict(text=f"<b>{resolved_x_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            automargin=True,
        ),
        yaxis=dict(
            title=dict(text=f"<b>{resolved_y_label}</b>", font=dict(size=14)),
            showgrid=True,
            gridcolor="rgba(200, 200, 200, 0.2)",
            automargin=True,
        ),
        template=theme,
        hovermode="closest",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=80, r=40, t=120, b=100),
        height=600,
        font=dict(family="Arial, sans-serif", size=12, color="#2c3e50"),
        hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial, sans-serif"),
    )

    chart_url = _save_plotly_chart(fig, title)
    return f"\n\n![{title}]({chart_url})\n\n"
