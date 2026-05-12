"""Domain models for dashboard module."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

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
from apps.shared.domain.base_domain_model import BaseDomainModel

PARAM_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TimePreset(StrEnum):
    """Predefined time range presets for relative time filtering."""

    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_YEAR = "this_year"


def _is_iso_datetime_string(value: Any) -> bool:
    """Return True if value is an ISO datetime/date string."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def normalize_time_range_value(value: Any) -> Any:
    """Normalize time_range value to supported canonical shape.

    Supported forms:
    - Relative: {"mode": "relative", "preset": "last_7_days"}
    - Absolute: {"mode": "absolute", "start": "...", "end": "..."}

    Legacy shorthand like {"start": "now-30d", "end": "now"} falls back
    to default relative last_7_days.
    """
    default_value = {"mode": "relative", "preset": TimePreset.LAST_7_DAYS.value}

    if value is None:
        return default_value

    if not isinstance(value, dict):
        return value

    mode = value.get("mode")
    if mode in {"relative", "custom", "absolute"}:
        return value

    if isinstance(value.get("preset"), str):
        return {**value, "mode": "relative"}

    if "start" in value and "end" in value:
        start = value.get("start")
        end = value.get("end")
        if _is_iso_datetime_string(start) and _is_iso_datetime_string(end):
            return {**value, "mode": "absolute"}
        if isinstance(start, str) and start.startswith("now-") and end == "now":
            return default_value

    return value


@dataclass
class GaugeDisplayConfig:
    """Display configuration for gauge charts.

    Uses a focused sub-config to avoid bloating the base display config.
    """

    min_value: float | None = None
    """Minimum value of the gauge scale."""

    max_value: float | None = None
    """Maximum value of the gauge scale."""

    unit: str | None = None
    """Unit suffix for gauge value display (e.g., %, ms)."""

    thresholds: list[tuple[float, str]] | None = None
    """Color thresholds as (ratio, color) pairs, ratio in [0, 1]."""

    start_angle: int | None = None
    """Gauge start angle in degrees."""

    end_angle: int | None = None
    """Gauge end angle in degrees."""

    show_detail: bool | None = None
    """Whether to show the center detail value."""

    show_axis_label: bool | None = None
    """Whether to show axis labels around the gauge."""


@dataclass
class ScatterDisplayConfig:
    """Display configuration for scatter charts."""

    size_range: tuple[int, int] | None = None
    """Size range for scatter plot bubbles in pixels: (min_px, max_px).

    Used to map data values to visual bubble sizes.
    Example: (5, 50) means smallest bubble is 5px, largest is 50px.
    """

    color_scale_type: ColorScaleType | None = None
    """Color scale type for visualization: linear, ordinal, or log.

    - 'linear': for continuous numeric data
    - 'ordinal': for categorical data
    - 'log': for data with exponential distribution
    """

    color_range: tuple[str, str] | None = None
    """Color range as hex values: (start_color, end_color).

    Example: ("#FF0000", "#00FF00") for red to green gradient.
    Used with color_scale_type to define the color mapping.
    """


@dataclass
class TableValueFormat:
    """Formatting options for table cell values."""

    format_type: TableFormatType | None = None
    """Format type: string, number, currency, percent, datetime, boolean."""

    precision: int | None = None
    """Decimal precision for numeric formats."""

    currency: str | None = None
    """Currency code for currency format (e.g., USD, CNY)."""

    date_format: str | None = None
    """Datetime display format (e.g., YYYY-MM-DD)."""

    prefix: str | None = None
    """Prefix string displayed before the formatted value."""

    suffix: str | None = None
    """Suffix string displayed after the formatted value."""

    null_display: str | None = None
    """Fallback text for null/empty values (e.g., "-")."""

    true_label: str | None = None
    """Label for boolean true values."""

    false_label: str | None = None
    """Label for boolean false values."""


@dataclass
class TableColumnConfig:
    """Display configuration for a single table column."""

    field: str
    """Data field name (column key) from the query result."""

    label: str | None = None
    """Header label for the column."""

    align: TableAlign | None = None
    """Text alignment: left, center, right."""

    width: int | None = None
    """Fixed width in pixels."""

    min_width: int | None = None
    """Minimum width in pixels."""

    max_width: int | None = None
    """Maximum width in pixels."""

    format: TableValueFormat | None = None
    """Per-column formatting override."""


@dataclass
class TableDisplayConfig:
    """Display configuration for table widgets.

    Provides header labels and per-column formatting for numeric/date values.
    """

    columns: list[TableColumnConfig] | None = None
    """Optional ordered list of columns. If None, UI can infer from data."""

    default_format: TableValueFormat | None = None
    """Default formatting applied when a column has no specific format."""

    show_header: bool = True
    """Whether to show table headers."""

    show_row_numbers: bool = False
    """Whether to show row index numbers."""

    zebra_stripes: bool | None = None
    """Whether to render alternating row background colors."""

    compact: bool | None = None
    """Whether to use a compact row height."""


@dataclass
class ChartDisplayConfig:
    """Display configuration for chart widgets.

    Provides metadata for better visualization including titles, axis labels,
    and series descriptions. All fields are optional for backward compatibility.

    Examples:
        Line chart with labels:
            ChartDisplayConfig(
                title="Daily Sales Trend",
                x_label="Date",
                y_label="Revenue (USD)",
                series_labels={"daily_sales": "Sales Amount"}
            )

        Metric widget with format:
            ChartDisplayConfig(
                title="Total Orders",
                metric_format="number"
            )
    """

    title: str | None = None
    """Widget title displayed at the top."""

    description: str | None = None
    """Optional widget description or subtitle."""

    x_label: str | None = None
    """X-axis label (for chart widgets)."""

    y_label: str | None = None
    """Y-axis label (for chart widgets)."""

    series_labels: dict[str, str] | None = None
    """Maps data column names to display names. E.g., {"col_name": "Display Name"}"""

    show_legend: bool = True
    """Whether to show legend for multi-series charts."""

    legend_position: LegendPosition | None = None
    """Legend position: top, bottom, left, or right."""

    metric_format: MetricFormat | None = None
    """Format for metric widgets only: number, currency, or percent."""

    scatter: ScatterDisplayConfig | None = None
    """Scatter chart-specific display configuration."""

    gauge: GaugeDisplayConfig | None = None
    """Gauge-specific display configuration.

    This is intentionally nested to avoid expanding the base display config.
    """

    table: TableDisplayConfig | None = None
    """Table widget-specific display configuration (headers, formats)."""


@dataclass
class WidgetPosition:
    """Widget position in grid layout."""

    x: int
    y: int
    w: int  # width in grid columns
    h: int  # height in grid rows


@dataclass
class FieldMapping:
    """Field mapping for data transformation.

    Supports flexible mapping for different widget types:
    - Metric widget: uses 'value' to map the metric column
    - Axis-series charts (line/bar/area/grouped_bar/stacked_bar/multi_line/multi_area):
      uses 'x_axis' (category/time) + 'series' (values)
    - Pie chart: uses 'value' (numbers) and optionally x_axis (labels)
    - Scatter chart: uses 'x_axis', 'y_axis', optionally 'size' and 'color'
    - Heatmap chart: uses 'x_axis', 'y_axis', and 'value'
    - Table: usually no mapping needed (show all columns)

    The 'extra' field allows arbitrary additional mappings for custom needs,
    such as display_name, formatting, colors, etc.
    """

    x_axis: str | None = None
    """X-axis or horizontal axis field."""

    y_axis: str | None = None
    """Y-axis or vertical axis field. Required for scatter charts."""

    series: list[str] | list[dict[str, str]] | None = None
    """Series binding supports either:
    - list[str]: simple column names
    - list[dict[str, str]]: structured series descriptors (e.g., name, alias)
    UI/service should normalize to a consistent structure when rendering.
    """

    value: str | None = None
    """Value field for metric/pie charts."""

    size: str | None = None
    """Size field for scatter charts. Maps data values to bubble sizes."""

    color: str | None = None
    """Color field for scatter charts. Maps data values to colors."""

    extra: dict[str, Any] | None = None
    """Extensible for custom fields."""


@dataclass
class DashboardFilterOption:
    """Option for dropdown filters."""

    label: str
    value: Any


@dataclass
class DashboardFilterOptionsResult:
    """Resolved dropdown filter options with optional query error state."""

    options: list[DashboardFilterOption]
    has_error: bool = False
    error_message: str | None = None


@dataclass
class DashboardFilter:
    """Dashboard filter definition stored in configuration."""

    id: str
    name: str
    type: FilterType

    param_key: str | None = None
    """Template parameter key used for SQL placeholders (e.g., 'time')."""

    value: Any | None = None
    """Persisted filter value (supports time_range or dropdown values)."""

    data_source_id: int | None = None
    """Data source for dropdown_datasource options."""

    options_query: str | None = None
    """SQL query to load dropdown options (expects columns: value, label)."""

    options: list[DashboardFilterOption] | None = None
    """Static dropdown options."""

    allow_multiple: bool | None = None
    """Whether dropdown filters allow multiple selections."""

    time_precision: TimePrecision | None = None
    """Time precision for time_range filters: 'date' or 'datetime'.
    
    Only applicable when type='time_range'.
    - 'date': start at 00:00:00, end at 23:59:59 (local time boundary)
    - 'datetime': preserve exact datetime as selected by user
    
    Default is 'datetime' for backward compatibility.
    """

    description: str | None = None
    """Optional helper description for UI."""

    required: bool = False
    """Whether this filter must have a value before querying."""

    def get_normalized_param_key(self) -> str:
        """Get the parameter key for this filter.

        The param_key must follow SQL parameter naming rules:
        - Starts with a letter or underscore
        - Contains only letters, digits, and underscores

        Returns:
            Parameter key string

        Raises:
            ValueError: If param_key is missing or invalid
        """
        if not self.param_key:
            raise ValueError("Filter param_key is required")
        if not PARAM_KEY_PATTERN.match(self.param_key):
            raise ValueError(f"Invalid filter param_key: {self.param_key}")
        return self.param_key

    def get_param_names(self) -> list[str]:
        """Get all SQL parameter names generated by this filter.

        Examples:
            - time_range filter with param_key='time': ['start_time', 'end_time']
            - dropdown filter with param_key='category': ['category']
            - time_range filter without param_key: ['start_filter_xxx', 'end_filter_xxx']

        Returns:
            List of parameter names (without ':' prefix)
        """
        base_key = self.get_normalized_param_key()
        if self.type == "time_range":
            # Backward-compatible aliases:
            # - canonical: start_<param>, end_<param>
            # - legacy: <param>_start, <param>_end
            return [f"start_{base_key}", f"end_{base_key}", f"{base_key}_start", f"{base_key}_end"]
        return [base_key]

    def get_macro_template(self) -> str | None:
        """Get the macro template that can be used in widget SQL queries.

        Returns the recommended macro syntax for referencing this filter in queries.

        Returns:
            Macro template string, or None if filter type doesn't support macros

        Examples:
            - time_range: "$time_filter(:time, date_column)"
            - dropdown: "$in_or_equal(:category, category_column)"
        """
        base_key = self.get_normalized_param_key()
        if self.type == "time_range":
            return f"$time_filter(:{base_key}, <field_name>)"
        elif self.type in ("dropdown_static", "dropdown_datasource"):
            return f"$in_or_equal(:{base_key}, <field_name>)"
        return None

    def get_display_info(self) -> dict[str, Any]:
        """Get complete filter information for frontend display.

        Returns a dictionary containing all necessary information for the frontend
        to display available filter variables and macro helpers in widget editors.

        Returns:
            Dictionary with keys:
                - id: filter ID
                - name: filter display name
                - type: filter type
                - param_names: list of SQL parameter names
                - macro_template: recommended macro syntax
        """
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "param_names": self.get_param_names(),
            "macro_template": self.get_macro_template(),
        }


class TimeRangeResolver:
    """Business logic for resolving time range filters.

    Handles both absolute (ISO datetime) and relative (preset-based) modes.
    Converts time presets and user-selected local times to UTC datetime tuples at query time.

    Key behaviors:
    - Accepts local datetime input from frontend (no timezone info)
    - Applies precision rules (date → add time boundaries)
    - Returns UTC-aware datetime tuples for backend queries
    """

    @staticmethod
    def _parse_local_datetime(value: Any) -> datetime | None:
        """Parse local datetime from string format.

        Frontend sends local datetime strings (no timezone info).
        This parses them as naive datetime (assumes local time).

        Args:
            value: ISO format string (e.g., '2026-01-25' or '2026-01-25T14:30:00')

        Returns:
            Naive datetime (local time, no tzinfo)
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            # If already datetime, return as-is (assume local if naive)
            return value
        if isinstance(value, str):
            try:
                # Parse without timezone info - treat as local time
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def resolve(
        value: Any, precision: str | TimePrecision | None = None, local_tz_offset: int | None = None
    ) -> tuple[datetime, datetime] | None:
        """Resolve time range value to (start, end) UTC datetime tuple.

        Handles both relative (preset-based) and absolute (user-selected) modes.
        Converts from local time to UTC, applying precision rules.

        Args:
            value: Time range value dict with 'mode' key:
                - Absolute: {mode: 'absolute', start: 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:mm', end: '...'}
                - Relative: {mode: 'relative', preset: TimePreset.value}
            precision: Time precision ('date' or 'datetime'). Defaults to 'datetime'.
                - 'date': end time is set to 23:59:59
                - 'datetime': preserve exact time
            local_tz_offset: UTC offset in seconds (for converting local to UTC).
                If None, assumes system local timezone.

        Returns:
            Tuple of (start_datetime, end_datetime) both in UTC, or None if invalid

        Examples:
            # User selects 2026-01-25 to 2026-01-26 with date precision
            # Frontend sends: {mode: 'absolute', start: '2026-01-25', end: '2026-01-26'}
            # Result: (2026-01-25 00:00:00 UTC, 2026-01-26 23:59:59 UTC)

            # User selects 2026-01-25T14:30 to 2026-01-26T10:15 with datetime precision
            # Assuming UTC+8 timezone (offset=28800):
            # Result: (2026-01-25 06:30:00 UTC, 2026-01-26 02:15:00 UTC)
        """
        if not isinstance(value, dict):
            return None

        mode = value.get("mode")
        now = datetime.now(UTC)

        # Default precision to 'datetime' for backward compatibility
        if precision is None:
            precision = "datetime"

        if mode == "absolute":
            start = TimeRangeResolver._parse_local_datetime(value.get("start"))
            end = TimeRangeResolver._parse_local_datetime(value.get("end"))

            if not start or not end:
                return None

            # Convert local time to UTC
            start_utc = TimeRangeResolver._local_to_utc(start, local_tz_offset)
            end_utc = TimeRangeResolver._local_to_utc(end, local_tz_offset)

            # Apply precision rules
            if precision == "date":
                # Start: 00:00:00 local → 00:00:00 local → convert to UTC
                # End: 23:59:59 local → convert to UTC
                start_utc = TimeRangeResolver._local_to_utc(
                    start.replace(hour=0, minute=0, second=0, microsecond=0), local_tz_offset
                )
                end_utc = TimeRangeResolver._local_to_utc(
                    end.replace(hour=23, minute=59, second=59, microsecond=999999), local_tz_offset
                )

            return start_utc, end_utc

        if mode == "relative":
            preset = value.get("preset")

            # For relative presets, resolve in UTC using 'now' as reference
            # Precision doesn't apply to presets (they're already defined)
            if preset == TimePreset.TODAY:
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                return start, now

            if preset == TimePreset.YESTERDAY:
                start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                return start, end

            if preset == TimePreset.LAST_7_DAYS:
                return now - timedelta(days=7), now

            if preset == TimePreset.LAST_30_DAYS:
                return now - timedelta(days=30), now

            if preset == TimePreset.THIS_MONTH:
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                return start, now

            if preset == TimePreset.LAST_MONTH:
                first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                last_month_end = first_of_this_month - timedelta(days=1)
                start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                return start, first_of_this_month

            if preset == TimePreset.THIS_YEAR:
                start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                return start, now

        return None

    @staticmethod
    def _local_to_utc(local_dt: datetime, tz_offset: int | None = None) -> datetime:
        """Convert naive local datetime to UTC-aware datetime.

        Args:
            local_dt: Naive datetime (treated as local time)
            tz_offset: UTC offset in seconds. If None, uses system local timezone.

        Returns:
            UTC-aware datetime
        """
        if tz_offset is None:
            # Use system's local timezone
            import time as time_module

            tz_offset = -time_module.timezone if not time_module.daylight else -time_module.altzone

        # Convert: local_time - offset = UTC
        utc_dt = local_dt - timedelta(seconds=tz_offset)
        return utc_dt.replace(tzinfo=UTC)


@dataclass
class DashboardWidget:
    """Widget configuration with integrated data binding."""

    id: str
    type: WidgetType
    position: WidgetPosition
    chart_type: ChartType | None = None

    # Display configuration (domain layer)
    display_config: ChartDisplayConfig | None = None
    """Domain-level display configuration (titles, labels, legend, formatting).
    
    This represents business/semantic metadata about how the widget should be presented.
    UI layer transforms this into renderer-specific options (e.g., Echarts config).
    """

    # UI render overrides (presentation layer)
    options: dict[str, Any] | None = None
    """Optional UI/render-layer overrides for advanced customization.

    Use this for renderer-specific settings (colors, animations, interactions) that
    override defaults generated from display_config. Business logic should not depend on it.
    """

    # Data binding fields (optional for text/filter widgets)
    data_source_id: int | None = None
    query: str | None = None
    field_mapping: FieldMapping | None = None


@dataclass
class DashboardLayout:
    """Dashboard layout configuration."""

    type: LayoutType = "grid"
    """Layout mode: 'grid' for CSS Grid-based responsive layout, 'flex' for flexbox (future)."""

    cols: int = 12
    """Number of grid columns. Responsive grid constraint: widget width (w) + x position must be <= cols.
    
    Example:
    - 12 columns (default): standard responsive grid with 12-column layout
    - Each widget position x + width (w) cannot exceed this value
    - If violated, widget width is automatically clamped to fit
    """

    rows: int = 12
    """Number of grid rows. Initial visible rows; grid can expand dynamically as widgets overflow.
    
    Example:
    - 12 rows: can display up to 12 rows; if needed, grid extends beyond
    - Each widget occupies h (height) grid rows
    """

    gap: int = 16
    """Spacing between widgets in pixels (CSS Grid gap property).
    
    Example:
    - 16px (default): 16 pixels of space between adjacent widgets
    - Applied both horizontally and vertically
    """

    row_height: int = 80
    """Height of each grid row in pixels. Defines vertical scale.
    
    Example:
    - 80px (default): each grid row is 80 pixels tall
    - Widget height: h=3 means 3 rows = 3 * 80 = 240 pixels
    - Used for responsive calculations on frontend
    """


@dataclass
class DashboardConfig:
    """Complete dashboard configuration."""

    layout: DashboardLayout
    widgets: list[DashboardWidget]
    filters: list[DashboardFilter] | None = None

    def get_widget_by_id(self, widget_id: str) -> DashboardWidget | None:
        """Find a widget by its ID.

        Args:
            widget_id: The widget ID to search for

        Returns:
            The DashboardWidget if found, None otherwise
        """
        for widget in self.widgets:
            if widget.id == widget_id:
                return widget
        return None

    def get_filter_by_id(self, filter_id: str) -> DashboardFilter | None:
        """Find a filter by its ID."""
        if not self.filters:
            return None
        for dashboard_filter in self.filters:
            if dashboard_filter.id == filter_id:
                return dashboard_filter
        return None


@dataclass
class DashboardDomain(BaseDomainModel):
    """Dashboard domain model."""

    id: int
    tenant_id: int
    name: str
    description: str | None
    config: DashboardConfig
    owner_id: int
    created_at: datetime
    updated_at: datetime
    owner_username: str | None = None

    def get_widget_by_id(self, widget_id: str) -> DashboardWidget | None:
        """Find a widget by its ID.

        Args:
            widget_id: The widget ID to search for

        Returns:
            The DashboardWidget if found, None otherwise
        """
        return self.config.get_widget_by_id(widget_id)


# ============================================================================
# Default Layout Configuration
# ============================================================================

DEFAULT_DASHBOARD_LAYOUT = DashboardLayout(
    type="grid",
    cols=12,
    rows=12,
    gap=16,
    row_height=80,
)
"""Default dashboard layout with 12-column responsive grid.

Usage:
    from apps.shared.dashboard.domain import DEFAULT_DASHBOARD_LAYOUT, DashboardConfig
    
    config = DashboardConfig(
        layout=DEFAULT_DASHBOARD_LAYOUT,
        widgets=[],
    )
"""
