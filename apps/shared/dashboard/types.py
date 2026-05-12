"""Shared type definitions for dashboard module.

This module contains all type aliases and enums used across domain, DTO, and adapter layers.
Centralizing types here ensures consistency and reduces duplication.
"""

from typing import Literal

from apps.shared.chart.types import ChartType as SharedChartType

# Widget and Chart Types
WidgetType = Literal["chart", "table", "metric", "filter", "text"]
"""Widget type enumeration: chart, table, metric, filter, or text."""

# Dashboard widget ChartType is intentionally aligned with the shared chart model.
# Frontend ECharts builders in apps/tenant_app_portal/src/lib/dashboardChart.ts
# must support every value in this alias.
ChartType = SharedChartType
"""Chart type enumeration for dashboard widgets (ECharts-rendered in browser)."""

# Display Configuration Types
LegendPosition = Literal["top", "bottom", "left", "right"]
"""Legend position for charts: top, bottom, left, or right."""

MetricFormat = Literal["number", "currency", "percent"]
"""Format type for metric widgets: number, currency, or percent."""

ColorScaleType = Literal["linear", "ordinal", "log"]
"""Color scale type for visualizations: linear, ordinal, or log."""

# Table Configuration Types
TableAlign = Literal["left", "center", "right"]
"""Text alignment for table columns: left, center, or right."""

TableFormatType = Literal["string", "number", "currency", "percent", "datetime", "boolean"]
"""Value format type for table cells: string, number, currency, percent, datetime, or boolean."""

# Filter Types
FilterType = Literal["time_range", "dropdown_static", "dropdown_datasource"]
"""Filter type enumeration: time_range, dropdown_static, or dropdown_datasource."""

TimePrecision = Literal["date", "datetime"]
"""Time precision for time_range filters: date (with 00:00:00/23:59:59 boundaries) or datetime (exact time)."""

FilterOperator = Literal["=", "!=", ">", ">=", "<", "<=", "in", "between", "like", "ilike"]
"""SQL filter operators for query building."""

# Layout Types
LayoutType = Literal["grid", "flex"]
"""Dashboard layout mode: grid (CSS Grid) or flex (flexbox, future)."""
