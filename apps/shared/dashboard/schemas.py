"""DTOs for dashboard module."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.shared.artifact.schemas import Artifact
from apps.shared.dashboard.domain import DashboardDomain, normalize_time_range_value
from apps.shared.dashboard.types import (
    ChartType,
    ColorScaleType,
    FilterType,
    LayoutType,
    LegendPosition,
    MetricFormat,
    TableAlign,
    TableFormatType,
    TimePrecision,
    WidgetType,
)

# ============================================================================
# Configuration DTOs (Pydantic models for API/Tool layer)
# ============================================================================


class TableValueFormatDTO(BaseModel):
    """Table cell value formatting options."""

    format_type: TableFormatType | None = Field(
        default=None, alias="formatType", description="Format type for the value"
    )
    precision: int | None = Field(default=None, description="Decimal precision for numeric formats")
    currency: str | None = Field(default=None, description="Currency code (e.g., USD, CNY)")
    date_format: str | None = Field(default=None, alias="dateFormat", description="Datetime format (e.g., YYYY-MM-DD)")
    prefix: str | None = Field(default=None, description="Prefix string")
    suffix: str | None = Field(default=None, description="Suffix string")
    null_display: str | None = Field(
        default=None, alias="nullDisplay", description='Fallback for null values (e.g., "-")'
    )
    true_label: str | None = Field(default=None, alias="trueLabel", description="Label for boolean true")
    false_label: str | None = Field(default=None, alias="falseLabel", description="Label for boolean false")

    model_config = ConfigDict(populate_by_name=True)


class TableColumnConfigDTO(BaseModel):
    """Table column display configuration."""

    field: str = Field(..., description="Data field name (column key)")
    label: str | None = Field(default=None, description="Column header label")
    align: TableAlign | None = Field(default=None, description="Text alignment")
    width: int | None = Field(default=None, description="Fixed width in pixels")
    min_width: int | None = Field(default=None, alias="minWidth", description="Minimum width in pixels")
    max_width: int | None = Field(default=None, alias="maxWidth", description="Maximum width in pixels")
    format: TableValueFormatDTO | None = Field(default=None, description="Per-column formatting")

    model_config = ConfigDict(populate_by_name=True)


class TableDisplayConfigDTO(BaseModel):
    """Table widget display configuration."""

    columns: list[TableColumnConfigDTO] | None = Field(
        default=None, description="Column configurations (if None, infer from data)"
    )
    default_format: TableValueFormatDTO | None = Field(
        default=None, alias="defaultFormat", description="Default formatting for all columns"
    )
    show_header: bool = Field(default=True, alias="showHeader", description="Whether to show table headers")
    show_row_numbers: bool = Field(
        default=False, alias="showRowNumbers", description="Whether to show row index numbers"
    )
    zebra_stripes: bool | None = Field(default=None, alias="zebraStripes", description="Alternating row colors")
    compact: bool | None = Field(default=None, description="Use compact row height")

    model_config = ConfigDict(populate_by_name=True)


class GaugeDisplayConfigDTO(BaseModel):
    """Gauge chart display configuration."""

    min_value: float | None = Field(default=None, alias="minValue", description="Minimum gauge value")
    max_value: float | None = Field(default=None, alias="maxValue", description="Maximum gauge value")
    unit: str | None = Field(default=None, description="Unit suffix (e.g., %, ms)")
    thresholds: list[tuple[float, str]] | None = Field(
        default=None, description="Color thresholds as [(ratio, color)] pairs"
    )
    start_angle: int | None = Field(default=None, alias="startAngle", description="Gauge start angle in degrees")
    end_angle: int | None = Field(default=None, alias="endAngle", description="Gauge end angle in degrees")
    show_detail: bool | None = Field(default=None, alias="showDetail", description="Show center detail value")
    show_axis_label: bool | None = Field(default=None, alias="showAxisLabel", description="Show axis labels")

    model_config = ConfigDict(populate_by_name=True)


class ScatterDisplayConfigDTO(BaseModel):
    """Scatter chart display configuration."""

    size_range: tuple[int, int] | None = Field(
        default=None, alias="sizeRange", description="Bubble size range in pixels: (min, max)"
    )
    color_scale_type: ColorScaleType | None = Field(
        default=None, alias="colorScaleType", description="Color scale type"
    )
    color_range: tuple[str, str] | None = Field(
        default=None, alias="colorRange", description="Color range as hex: (start, end)"
    )

    model_config = ConfigDict(populate_by_name=True)


class ChartDisplayConfigDTO(BaseModel):
    """Chart widget display configuration with titles, labels, and formatting."""

    title: str | None = Field(default=None, description="Widget title")
    description: str | None = Field(default=None, description="Widget description or subtitle")
    x_label: str | None = Field(default=None, alias="xLabel", description="X-axis label")
    y_label: str | None = Field(default=None, alias="yLabel", description="Y-axis label")
    series_labels: dict[str, str] | None = Field(
        default=None, alias="seriesLabels", description='Maps column names to display names: {"col": "Display Name"}'
    )
    show_legend: bool = Field(default=True, alias="showLegend", description="Show legend for multi-series charts")
    legend_position: LegendPosition | None = Field(default=None, alias="legendPosition", description="Legend position")
    metric_format: MetricFormat | None = Field(
        default=None, alias="metricFormat", description="Format for metric widgets"
    )
    scatter: ScatterDisplayConfigDTO | None = Field(default=None, description="Scatter chart specific config")
    gauge: GaugeDisplayConfigDTO | None = Field(default=None, description="Gauge chart specific config")
    table: TableDisplayConfigDTO | None = Field(default=None, description="Table widget specific config")

    model_config = ConfigDict(populate_by_name=True)


class WidgetPositionDTO(BaseModel):
    """Widget position in grid layout."""

    x: int = Field(..., description="X position (column index, 0-based)")
    y: int = Field(..., description="Y position (row index, 0-based)")
    w: int = Field(..., description="Width in grid columns")
    h: int = Field(..., description="Height in grid rows")


class FieldMappingDTO(BaseModel):
    """Field mapping for data transformation in widgets."""

    x_axis: str | None = Field(default=None, alias="xAxis", description="X-axis field (category/time)")
    y_axis: str | None = Field(default=None, alias="yAxis", description="Y-axis field (required for scatter)")
    series: list[str] | list[dict[str, str]] | None = Field(
        default=None, description="Series fields: list of column names or structured descriptors"
    )
    value: str | None = Field(default=None, description="Value field for metric/pie charts")
    size: str | None = Field(default=None, description="Size field for scatter charts (bubble size)")
    color: str | None = Field(default=None, description="Color field for scatter charts")
    extra: dict[str, Any] | None = Field(default=None, description="Additional custom mappings")

    model_config = ConfigDict(populate_by_name=True)


class DashboardWidgetDTO(BaseModel):
    """Dashboard widget configuration."""

    id: str = Field(..., description="Widget unique ID")
    type: WidgetType = Field(..., description="Widget type")
    position: WidgetPositionDTO = Field(..., description="Widget position in grid (x, y, w, h)")
    chart_type: ChartType | None = Field(default=None, alias="chartType", description="Chart type (for chart widgets)")
    display_config: ChartDisplayConfigDTO | None = Field(
        default=None,
        alias="displayConfig",
        description="Display configuration (titles, labels, legend, formatting)",
    )
    options: dict[str, Any] | None = Field(
        default=None, description="UI-level render overrides for advanced customization"
    )
    data_source_id: int | None = Field(default=None, alias="dataSourceId", description="Data source ID")
    query: str | None = Field(default=None, description="SQL query for data binding")
    field_mapping: FieldMappingDTO | None = Field(
        default=None, alias="fieldMapping", description="Field mapping for data transformation"
    )

    model_config = ConfigDict(populate_by_name=True)


class DashboardFilterOptionDTO(BaseModel):
    """Filter dropdown option."""

    label: str = Field(..., description="Option display label")
    value: Any = Field(..., description="Option value")


class DashboardFilterDTO(BaseModel):
    """Dashboard filter configuration."""

    id: str = Field(..., description="Filter unique ID")
    name: str = Field(..., description="Filter display name")
    type: FilterType = Field(..., description="Filter type")
    param_key: str | None = Field(
        default=None, alias="paramKey", description="SQL parameter key (e.g., 'time' for :time placeholder)"
    )
    value: Any | None = Field(default=None, description="Persisted filter value")
    data_source_id: int | None = Field(
        default=None, alias="dataSourceId", description="Data source for dropdown_datasource"
    )
    options_query: str | None = Field(
        default=None, alias="optionsQuery", description="SQL query for dropdown options (expects: value, label)"
    )
    options: list[DashboardFilterOptionDTO] | None = Field(default=None, description="Static dropdown options")
    allow_multiple: bool | None = Field(
        default=None, alias="allowMultiple", description="Allow multiple selections for dropdown"
    )
    time_precision: TimePrecision | None = Field(
        default=None, alias="timePrecision", description="Time precision for time_range filters: 'date' or 'datetime'"
    )
    description: str | None = Field(default=None, description="Filter helper description")
    required: bool | None = Field(default=False, description="Whether filter value is required")
    param_names: list[str] | None = Field(
        default=None,
        alias="paramNames",
        description="Resolved SQL parameter names derived from param_key",
    )
    macro_template: str | None = Field(
        default=None,
        alias="macroTemplate",
        description="Recommended SQL macro template for this filter",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _default_time_range_value(self) -> "DashboardFilterDTO":
        if self.type == "time_range":
            normalized = normalize_time_range_value(self.value)
            if normalized != self.value:
                self.value = normalized
        return self


class DashboardFilterUpdateDTO(BaseModel):
    """DTO for partial update of dashboard filter (all fields optional)."""

    name: str | None = Field(default=None, description="Filter display name")
    type: FilterType | None = Field(default=None, description="Filter type")
    param_key: str | None = Field(
        default=None, alias="paramKey", description="SQL parameter key (e.g., 'time' for :time placeholder)"
    )
    value: Any | None = Field(default=None, description="Persisted filter value")
    data_source_id: int | None = Field(
        default=None, alias="dataSourceId", description="Data source for dropdown_datasource"
    )
    options_query: str | None = Field(
        default=None, alias="optionsQuery", description="SQL query for dropdown options (expects: value, label)"
    )
    options: list[DashboardFilterOptionDTO] | None = Field(default=None, description="Static dropdown options")
    allow_multiple: bool | None = Field(
        default=None, alias="allowMultiple", description="Allow multiple selections for dropdown"
    )
    time_precision: TimePrecision | None = Field(
        default=None, alias="timePrecision", description="Time precision for time_range filters: 'date' or 'datetime'"
    )
    description: str | None = Field(default=None, description="Filter helper description")
    required: bool | None = Field(default=None, description="Whether filter value is required")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _normalize_time_range_value(self) -> "DashboardFilterUpdateDTO":
        if self.type == "time_range":
            normalized = normalize_time_range_value(self.value)
            if normalized != self.value:
                self.value = normalized
        return self


class DashboardLayoutDTO(BaseModel):
    """Dashboard layout configuration."""

    type: LayoutType = Field(
        default="grid", description="Layout mode: 'grid' for CSS Grid, 'flex' for flexbox (future)"
    )
    cols: int = Field(default=12, description="Number of grid columns (widget x + w must be <= cols)")
    rows: int = Field(default=12, description="Number of grid rows (can expand dynamically)")
    gap: int = Field(default=16, description="Spacing between widgets in pixels")
    row_height: int = Field(
        default=80, alias="rowHeight", description="Height of each grid row in pixels (widget height = h * row_height)"
    )

    model_config = ConfigDict(populate_by_name=True)


class DashboardConfigDTO(BaseModel):
    """Complete dashboard configuration with layout, widgets, and filters."""

    layout: DashboardLayoutDTO = Field(..., description="Dashboard grid layout configuration")
    widgets: list[DashboardWidgetDTO] = Field(..., description="List of dashboard widgets")
    filters: list[DashboardFilterDTO] | None = Field(
        default=None, description="Dashboard-level filters for data query (time_range, dropdown)"
    )


# ============================================================================
# Request/Response DTOs
# ============================================================================


class DashboardCreate(BaseModel):
    """Dashboard creation request."""

    name: str = Field(..., min_length=1, max_length=255, description="Dashboard name")
    description: str | None = Field(default=None, description="Dashboard description")
    config: DashboardConfigDTO = Field(..., description="Dashboard configuration (layout, widgets, filters)")
    thread_id: str | None = Field(default=None, description="Optional agent thread ID for auto-linking artifact")


class DashboardUpdate(BaseModel):
    """Dashboard update request."""

    name: str | None = Field(
        default=None,
        alias="title",
        min_length=1,
        max_length=255,
        description="Dashboard title",
    )
    description: str | None = Field(default=None, description="Dashboard description")
    layout: DashboardLayoutDTO | None = Field(default=None, description="Dashboard layout configuration")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class DashboardWidgetCreateRequest(BaseModel):
    """Dashboard widget create request."""

    type: WidgetType = Field(..., description="Widget type")
    chart_type: ChartType | None = Field(default=None, alias="chartType", description="Chart type")
    position: WidgetPositionDTO = Field(..., description="Widget position in dashboard grid")
    data_source_id: int | None = Field(default=None, alias="dataSourceId", description="Data source ID")
    query: str | None = Field(default=None, description="SQL query for widget data binding")
    field_mapping: FieldMappingDTO | None = Field(
        default=None,
        alias="fieldMapping",
        description="Field mapping for data transformation",
    )
    display_config: ChartDisplayConfigDTO | None = Field(
        default=None,
        alias="displayConfig",
        description="Display configuration",
    )

    model_config = ConfigDict(populate_by_name=True)


class DashboardWidgetUpdateRequest(BaseModel):
    """Dashboard widget update request."""

    chart_type: ChartType | None = Field(default=None, alias="chartType", description="Chart type")
    position: WidgetPositionDTO | None = Field(default=None, description="Widget position in dashboard grid")
    data_source_id: int | None = Field(default=None, alias="dataSourceId", description="Data source ID")
    query: str | None = Field(default=None, description="SQL query for widget data binding")
    field_mapping: FieldMappingDTO | None = Field(
        default=None,
        alias="fieldMapping",
        description="Field mapping for data transformation",
    )
    display_config: ChartDisplayConfigDTO | None = Field(
        default=None,
        alias="displayConfig",
        description="Display configuration",
    )

    model_config = ConfigDict(populate_by_name=True)


class DashboardFilterCreateRequest(BaseModel):
    """Dashboard filter create request."""

    name: str = Field(..., description="Filter display name")
    type: FilterType = Field(..., description="Filter type")
    param_key: str | None = Field(
        default=None,
        alias="paramKey",
        description="SQL parameter key",
    )
    value: Any | None = Field(default=None, description="Persisted filter values for static dropdown or timerange")
    data_source_id: int | None = Field(default=None, alias="dataSourceId", description="Data source for options")
    options_query: str | None = Field(
        default=None,
        alias="optionsQuery",
        description="SQL query for datasource dropdown options",
    )
    options: list[DashboardFilterOptionDTO] | None = Field(default=None, description="Static dropdown options")
    allow_multiple: bool | None = Field(
        default=None,
        alias="allowMultiple",
        description="Allow multiple selections",
    )
    time_precision: TimePrecision | None = Field(
        default=None,
        alias="timePrecision",
        description="Time precision for time_range",
    )
    description: str | None = Field(default=None, description="Filter helper description")
    required: bool | None = Field(default=False, description="Whether filter value is required")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _default_time_range_value(self) -> "DashboardFilterCreateRequest":
        if self.type == "time_range":
            normalized = normalize_time_range_value(self.value)
            if normalized != self.value:
                self.value = normalized
        return self


# ============================================================================
# Tool Argument Schemas
# ============================================================================


class DashboardWidgetToolCreatePayload(BaseModel):
    """Dashboard widget create payload for agent tool usage."""

    widget_type: WidgetType = Field(..., description="Widget type: chart, table, metric, filter, or text")
    chart_type: ChartType | None = Field(
        default=None,
        description=(
            "Chart type for chart widgets. Supported: line, bar, area, pie, scatter, heatmap, "
            "stacked_bar, grouped_bar, multi_line, multi_area, gauge"
        ),
    )
    position: WidgetPositionDTO | None = Field(
        default=None,
        description="Grid position (x, y, w, h). If omitted, service auto-places the widget.",
    )
    data_source_id: int | None = Field(default=None, description="Data source ID for SQL query execution")
    query: str | None = Field(default=None, description="Read-only SQL query used for widget data binding")
    field_mapping: FieldMappingDTO | None = Field(
        default=None,
        description="Mapping from query columns to widget fields (xAxis/yAxis/series/value/size/color)",
    )
    display_config: ChartDisplayConfigDTO | None = Field(
        default=None,
        description="Display metadata (title, labels, legend, formatting)",
    )


class DashboardWidgetToolAddRequest(BaseModel):
    """Tool args for adding a widget to a dashboard.

    This model is shared by agent tools to keep tool-call validation aligned
    with the API/domain contracts in this module.
    """

    dashboard_id: int = Field(..., description="Target dashboard ID")
    widget_data: DashboardWidgetToolCreatePayload = Field(
        ...,
        description="Widget payload. Contains all widget configuration parameters.",
    )


class DashboardWidgetToolUpdateRequest(BaseModel):
    """Tool args for updating an existing widget."""

    dashboard_id: int = Field(..., description="Target dashboard ID")
    widget_id: str = Field(..., description="Widget ID in the dashboard")
    chart_type: ChartType | None = Field(
        default=None,
        description=(
            "New chart type for chart widgets. Supported: line, bar, area, pie, scatter, heatmap, "
            "stacked_bar, grouped_bar, multi_line, multi_area, gauge"
        ),
    )
    position: WidgetPositionDTO | None = Field(default=None, description="New grid position (x, y, w, h)")
    data_source_id: int | None = Field(default=None, description="Data source ID for SQL query execution")
    query: str | None = Field(default=None, description="New read-only SQL query")
    field_mapping: FieldMappingDTO | None = Field(
        default=None,
        description="Updated mapping from query columns to widget fields",
    )
    display_config: ChartDisplayConfigDTO | None = Field(
        default=None,
        description="Updated display metadata (title, labels, legend, formatting)",
    )


class DashboardWidgetToolValidateRequest(BaseModel):
    """Tool args for validating SQL via dashboard-scoped preview (compile + execute, limited rows)."""

    dashboard_id: int = Field(..., description="Dashboard ID (provides filter macros)")
    data_source_id: int = Field(..., description="Data source ID")
    query: str = Field(..., min_length=1, description="SQL SELECT query")


class DashboardFilterToolAddRequest(BaseModel):
    """Tool args for adding a filter to a dashboard."""

    dashboard_id: int = Field(..., description="Target dashboard ID")
    filter_data: DashboardFilterCreateRequest = Field(
        ...,
        description="Filter payload. ID is generated by service, so it is intentionally not part of this schema.",
    )


class DashboardFilterToolUpdateRequest(BaseModel):
    """Tool args for updating a filter on a dashboard."""

    dashboard_id: int = Field(..., description="Target dashboard ID")
    filter_id: str = Field(..., description="Filter ID in the dashboard")
    updates: DashboardFilterUpdateDTO = Field(..., description="Partial filter update payload")


class DashboardFilterToolRemoveRequest(BaseModel):
    """Tool args for removing a filter from a dashboard."""

    dashboard_id: int = Field(..., description="Target dashboard ID")
    filter_id: str = Field(..., description="Filter ID in the dashboard")


class DashboardResponse(BaseModel):
    """Dashboard response."""

    id: int
    tenant_id: int
    name: str
    description: str | None
    config: DashboardConfigDTO = Field(..., description="Dashboard configuration (layout, widgets, filters)")
    owner_id: int
    created_at: datetime
    updated_at: datetime
    artifact: Artifact | None = Field(
        default=None,
        description="Optional linked artifact when created with thread context",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DashboardListItemResponse(BaseModel):
    """Lightweight dashboard list response."""

    id: int
    tenant_id: int
    name: str
    description: str | None
    owner_id: int
    owner_username: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


@dataclass
class DashboardCreateWithArtifactResult:
    """Result model for dashboard creation with optional thread-level artifact link."""

    dashboard: DashboardDomain
    artifact: Artifact | None = None


class DashboardFilterValueOverrideDTO(BaseModel):
    """Runtime filter value override for widget data queries."""

    id: str | None = Field(default=None, description="Dashboard filter ID")
    param_key: str | None = Field(default=None, alias="paramKey", description="SQL parameter key")
    value: Any = Field(default=None, description="Override value used for this query only")

    model_config = ConfigDict(populate_by_name=True)


class DashboardWidgetQueryDataRequest(BaseModel):
    """Optional runtime filters for widget data queries."""

    filters: list[DashboardFilterValueOverrideDTO] | None = Field(
        default=None,
        description="Current filter values. When omitted, saved dashboard filters are used.",
    )


class DashboardQueryPreviewRequest(BaseModel):
    """Dashboard widget query preview request."""

    data_source_id: int | None = Field(
        default=None,
        description="Optional data source ID override for preview",
    )
    query: str | None = Field(
        default=None,
        description="Optional SQL query override for preview",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum rows to return")


class DashboardSqlPreviewRequest(BaseModel):
    """Preview SQL using dashboard filter macros without referencing a saved widget."""

    data_source_id: int = Field(..., description="Data source ID for SQL execution")
    query: str = Field(..., min_length=1, description="SQL SELECT query")
    limit: int = Field(default=50, ge=1, le=200, description="Maximum rows to return")


class DashboardQueryPreviewColumn(BaseModel):
    """Query preview column metadata."""

    name: str
    type: str


class DashboardQueryPreviewResponse(BaseModel):
    """Query preview response payload."""

    columns: list[DashboardQueryPreviewColumn]
    rows: list[dict[str, Any]]


class DashboardFilterOptionResponse(BaseModel):
    """Dashboard filter option."""

    label: str
    value: Any


class DashboardFilterOptionsResponse(BaseModel):
    """Dashboard filter options response."""

    options: list[DashboardFilterOptionResponse]
    has_error: bool = Field(default=False, description="Whether option query failed")
    error_message: str | None = Field(default=None, description="Option query error message")


class ChartFromSQLRequest(BaseModel):
    """Request payload for creating a chart from SQL query results."""

    data_source_id: int = Field(..., alias="dataSourceId", description="Data source ID")
    sql_query: str = Field(..., alias="sqlQuery", min_length=1, description="SQL SELECT query")
    chart_type: str = Field(..., alias="chartType", description="Chart type")
    x_key: str = Field(..., alias="xKey", description="X-axis key")
    y_key: str | None = Field(
        default=None, alias="yKey", description="Y-axis key (not required for multi-series charts)"
    )
    title: str = Field(..., description="Chart title")
    x_label: str | None = Field(default=None, alias="xLabel", description="X-axis label")
    y_label: str | None = Field(default=None, alias="yLabel", description="Y-axis label")
    series_keys: list[str] | None = Field(default=None, alias="seriesKeys", description="Multi-series value keys")
    z_key: str | None = Field(default=None, alias="zKey", description="Heatmap value key")
    theme: str = Field(default="plotly_white", description="Plotly theme")

    model_config = ConfigDict(populate_by_name=True)


class ChartFromSQLResponse(BaseModel):
    """Response payload for chart generation from SQL."""

    data_source_id: int = Field(..., alias="dataSourceId")
    row_count: int = Field(..., alias="rowCount")
    chart_markdown: str = Field(..., alias="chartMarkdown")
    chart_url: str | None = Field(default=None, alias="chartUrl")

    model_config = ConfigDict(populate_by_name=True)
