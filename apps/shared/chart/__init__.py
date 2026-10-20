"""Shared chart rendering package.

Server-side Plotly SVG renderer and agent chart input types.
Dashboard widget chart kinds are defined in ``apps.shared.dashboard.types``.
"""

from apps.shared.chart.normalize import normalize_plotly_chart_type
from apps.shared.chart.renderer import render_chart
from apps.shared.chart.types import (
    AGENT_CHART_INPUT_TYPES,
    PLOTLY_CHART_TYPES,
    AgentChartInputType,
    ChartRenderResult,
    PlotlyChartType,
)

__all__ = [
    "AGENT_CHART_INPUT_TYPES",
    "PLOTLY_CHART_TYPES",
    "AgentChartInputType",
    "ChartRenderResult",
    "PlotlyChartType",
    "normalize_plotly_chart_type",
    "render_chart",
]
