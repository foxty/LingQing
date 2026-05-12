"""Shared chart rendering package.

Provides the canonical ChartType definition and the server-side Plotly SVG renderer.
Consumed by agent chart tools and future export pipelines.
Dashboard widget rendering stays frontend-only (ECharts via buildChartOptions()).
"""

from apps.shared.chart.renderer import render_chart
from apps.shared.chart.types import ChartType

__all__ = ["ChartType", "render_chart"]
