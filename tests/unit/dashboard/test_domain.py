"""Unit tests for dashboard domain models.

Tests cover:
- ChartDisplayConfig creation and defaults
- All field types and validations
- Edge cases and boundary conditions
"""

from apps.shared.dashboard.domain import (
    ChartDisplayConfig,
    DashboardWidget,
    FieldMapping,
    GaugeDisplayConfig,
    LegendPosition,
    MetricFormat,
    WidgetPosition,
)


class TestChartDisplayConfig:
    """Test ChartDisplayConfig domain model."""

    def test_create_empty_display_config(self):
        """Should create display config with all defaults."""
        config = ChartDisplayConfig()

        assert config.title is None
        assert config.x_label is None
        assert config.y_label is None
        assert config.series_labels is None
        assert config.show_legend is True  # Default is True
        assert config.legend_position is None
        assert config.metric_format is None
        assert config.description is None
        assert config.gauge is None

    def test_create_chart_display_config_with_title(self):
        """Should create display config with title only."""
        config = ChartDisplayConfig(title="Sales Dashboard")

        assert config.title == "Sales Dashboard"
        assert config.x_label is None
        assert config.show_legend is True

    def test_create_full_chart_display_config(self):
        """Should create display config with all chart fields."""
        config = ChartDisplayConfig(
            title="Revenue Trends",
            x_label="Month",
            y_label="Revenue ($)",
            series_labels={"monthly_revenue": "Monthly Revenue", "target": "Target"},
            show_legend=True,
            legend_position="top",
            description="Year-over-year comparison",
        )

        assert config.title == "Revenue Trends"
        assert config.x_label == "Month"
        assert config.y_label == "Revenue ($)"
        assert config.series_labels == {
            "monthly_revenue": "Monthly Revenue",
            "target": "Target",
        }
        assert config.show_legend is True
        assert config.legend_position == "top"
        assert config.description == "Year-over-year comparison"

    def test_create_metric_display_config(self):
        """Should create display config for metric widget."""
        config = ChartDisplayConfig(
            title="Total Orders",
            metric_format="number",
            description="All-time order count",
        )

        assert config.title == "Total Orders"
        assert config.metric_format == "number"
        assert config.description == "All-time order count"
        # Chart-specific fields should be None
        assert config.x_label is None
        assert config.y_label is None
        assert config.gauge is None

    def test_create_gauge_display_config(self):
        """Should create display config with gauge sub-config."""
        gauge = GaugeDisplayConfig(
            min_value=0,
            max_value=100,
            unit="%",
            thresholds=[(0.5, "#67e8f9"), (1.0, "#f87171")],
            start_angle=200,
            end_angle=-20,
            show_detail=True,
            show_axis_label=False,
        )

        config = ChartDisplayConfig(gauge=gauge)

        assert config.gauge is not None
        assert config.gauge.min_value == 0
        assert config.gauge.max_value == 100
        assert config.gauge.unit == "%"
        assert config.gauge.thresholds == [(0.5, "#67e8f9"), (1.0, "#f87171")]
        assert config.gauge.start_angle == 200
        assert config.gauge.end_angle == -20
        assert config.gauge.show_detail is True
        assert config.gauge.show_axis_label is False

    def test_legend_position_values(self):
        """Should accept all valid legend positions."""
        positions: list[LegendPosition] = ["top", "bottom", "left", "right"]

        for pos in positions:
            config = ChartDisplayConfig(legend_position=pos)
            assert config.legend_position == pos

    def test_metric_format_values(self):
        """Should accept all valid metric formats."""
        formats: list[MetricFormat] = ["number", "currency", "percent"]

        for fmt in formats:
            config = ChartDisplayConfig(metric_format=fmt)
            assert config.metric_format == fmt

    def test_show_legend_false(self):
        """Should allow disabling legend."""
        config = ChartDisplayConfig(show_legend=False)
        assert config.show_legend is False

    def test_series_labels_empty_dict(self):
        """Should handle empty series labels dict."""
        config = ChartDisplayConfig(series_labels={})
        assert config.series_labels == {}

    def test_series_labels_single_entry(self):
        """Should handle single series label."""
        config = ChartDisplayConfig(series_labels={"sales": "Daily Sales"})
        assert config.series_labels == {"sales": "Daily Sales"}

    def test_series_labels_multiple_entries(self):
        """Should handle multiple series labels."""
        labels = {
            "sales": "Sales",
            "orders": "Orders",
            "revenue": "Revenue",
        }
        config = ChartDisplayConfig(series_labels=labels)
        assert config.series_labels == labels
        assert len(config.series_labels) == 3

    def test_unicode_in_labels(self):
        """Should support unicode characters in labels."""
        config = ChartDisplayConfig(
            title="销售趋势",
            x_label="日期",
            y_label="销售额（元）",
            series_labels={"daily_sales": "每日销售"},
        )

        assert config.title == "销售趋势"
        assert config.x_label == "日期"
        assert config.y_label == "销售额（元）"
        assert config.series_labels["daily_sales"] == "每日销售"

    def test_long_strings(self):
        """Should handle long string values."""
        long_title = "A" * 500
        long_description = "B" * 1000

        config = ChartDisplayConfig(
            title=long_title,
            description=long_description,
        )

        assert len(config.title) == 500
        assert len(config.description) == 1000

    def test_special_characters_in_labels(self):
        """Should handle special characters in labels."""
        config = ChartDisplayConfig(
            title="Revenue (Q1-2024)",
            x_label="Date & Time",
            y_label="Amount ($USD)",
            series_labels={"col_1": "Series #1", "col_2": "Series @2"},
        )

        assert "$" in config.y_label
        assert "&" in config.x_label
        assert "#" in config.series_labels["col_1"]

    def test_immutability_after_creation(self):
        """Should allow field modification (dataclass is mutable by default)."""
        config = ChartDisplayConfig(title="Initial")
        config.title = "Updated"
        assert config.title == "Updated"

    def test_equality(self):
        """Should compare display configs by value."""
        config1 = ChartDisplayConfig(
            title="Test",
            x_label="X",
            y_label="Y",
        )
        config2 = ChartDisplayConfig(
            title="Test",
            x_label="X",
            y_label="Y",
        )

        assert config1 == config2

    def test_inequality(self):
        """Should detect differences in display configs."""
        config1 = ChartDisplayConfig(title="Test1")
        config2 = ChartDisplayConfig(title="Test2")

        assert config1 != config2


class TestWidgetPosition:
    """Test WidgetPosition domain model."""

    def test_create_position(self):
        """Should create valid widget position."""
        pos = WidgetPosition(x=0, y=0, w=6, h=4)

        assert pos.x == 0
        assert pos.y == 0
        assert pos.w == 6
        assert pos.h == 4


class TestFieldMapping:
    """Test FieldMapping domain model."""

    def test_create_chart_field_mapping(self):
        """Should create field mapping for chart."""
        mapping = FieldMapping(
            x_axis="date",
            series=["sales", "revenue"],
        )

        assert mapping.x_axis == "date"
        assert mapping.series == ["sales", "revenue"]

    def test_create_metric_field_mapping(self):
        """Should create field mapping for metric."""
        mapping = FieldMapping(value="total_count")

        assert mapping.value == "total_count"
        assert mapping.x_axis is None


class TestDashboardWidget:
    """Test DashboardWidget domain model."""

    def test_create_widget_with_display_config(self):
        """Should create widget with display configuration in options."""
        # Note: display config is stored in options dict, not a direct field
        widget = DashboardWidget(
            id="widget-1",
            type="chart",
            chart_type="line",
            position=WidgetPosition(x=0, y=0, w=12, h=6),
            options={
                "display": {
                    "title": "Test Chart",
                    "xLabel": "Date",
                    "yLabel": "Value",
                }
            },
        )

        assert widget.options["display"]["title"] == "Test Chart"
        assert widget.options["display"]["xLabel"] == "Date"
