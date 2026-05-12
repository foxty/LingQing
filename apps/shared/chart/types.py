"""Canonical chart type definitions shared across the platform.

These chart types are used by both the server-side renderer and dashboard
widgets. Keep frontend ECharts builders in sync with this literal.
"""

from typing import Literal

# All chart types supported by the platform.
# To add support for a new type, update both backend contracts and the
# frontend ECharts builder in apps/tenant_app_portal/src/lib/dashboardChart.ts.
ChartType = Literal[
    "line",
    "bar",
    "area",
    "pie",
    "scatter",
    "heatmap",
    "stacked_bar",
    "grouped_bar",
    "multi_line",
    "multi_area",
    "gauge",
]
