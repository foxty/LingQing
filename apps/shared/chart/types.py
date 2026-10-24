"""Types for server-side Plotly charts and agent chart tools.

Dashboard widget chart kinds live in ``apps.shared.dashboard.types`` (ECharts).
"""

from dataclasses import dataclass
from typing import Literal

# What agent tools document and prefer (multi-series via series_key + stacked).
AgentChartInputType = Literal[
    "bar",
    "horizontal_bar",
    "line",
    "area",
    "pie",
    "scatter",
    "heatmap",
    "waterfall",
    "box",
    "violin",
]

# All types ``render_chart`` accepts after normalization (includes legacy explicit names).
# Subsets of ``PlotlyChartType`` for specialized render paths (not all agent input types).
GridPanelChartType = Literal["bar", "horizontal_bar", "line", "pie"]
DistributionChartType = Literal["box", "violin"]

PlotlyChartType = Literal[
    "bar",
    "horizontal_bar",
    "line",
    "area",
    "pie",
    "scatter",
    "heatmap",
    "waterfall",
    "box",
    "violin",
    "grouped_bar",
    "stacked_bar",
    "multi_line",
    "multi_area",
]

AGENT_CHART_INPUT_TYPES: frozenset[str] = frozenset(
    {
        "bar",
        "horizontal_bar",
        "line",
        "area",
        "pie",
        "scatter",
        "heatmap",
        "waterfall",
        "box",
        "violin",
    }
)

GRID_PANEL_CHART_TYPES: frozenset[str] = frozenset({"bar", "horizontal_bar", "line", "pie"})

DISTRIBUTION_CHART_TYPES: frozenset[str] = frozenset({"box", "violin"})

PLOTLY_CHART_TYPES: frozenset[str] = frozenset(
    {
        "bar",
        "horizontal_bar",
        "line",
        "area",
        "pie",
        "scatter",
        "heatmap",
        "waterfall",
        "box",
        "violin",
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
