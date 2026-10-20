"""Types for server-side Plotly charts and agent chart tools.

Dashboard widget chart kinds live in ``apps.shared.dashboard.types`` (ECharts).
"""

from dataclasses import dataclass
from typing import Literal

# What agent tools document and prefer (multi-series via series_key + stacked).
AgentChartInputType = Literal[
    "bar",
    "line",
    "area",
    "pie",
    "scatter",
    "heatmap",
]

# All types ``render_chart`` accepts after normalization (includes legacy explicit names).
PlotlyChartType = Literal[
    "bar",
    "line",
    "area",
    "pie",
    "scatter",
    "heatmap",
    "grouped_bar",
    "stacked_bar",
    "multi_line",
    "multi_area",
]

AGENT_CHART_INPUT_TYPES: frozenset[str] = frozenset(
    {
        "bar",
        "line",
        "area",
        "pie",
        "scatter",
        "heatmap",
    }
)

PLOTLY_CHART_TYPES: frozenset[str] = frozenset(
    {
        "bar",
        "line",
        "area",
        "pie",
        "scatter",
        "heatmap",
        "grouped_bar",
        "stacked_bar",
        "multi_line",
        "multi_area",
    }
)


@dataclass(frozen=True)
class ChartRenderResult:
    """Raster + vector output from Plotly (no persistence or URLs)."""

    svg_bytes: bytes
    png_bytes: bytes
    title: str
