"""Unit tests for dashboard adapters (serialization/deserialization).

Tests cover:
- ChartDisplayConfig <-> dict conversion
- filter config serialization fields
- camelCase <-> snake_case mapping
- None handling
"""

from apps.shared.dashboard.adapters import (
    dashboard_config_to_dict,
    dict_to_dashboard_config,
    dict_to_display_config,
    display_config_to_dict,
)
from apps.shared.dashboard.domain import (
    ChartDisplayConfig,
    DashboardConfig,
    DashboardFilter,
    DashboardLayout,
    GaugeDisplayConfig,
    TableColumnConfig,
    TableDisplayConfig,
    TableValueFormat,
)


class TestDisplayConfigSerialization:
    """Test ChartDisplayConfig serialization and deserialization."""

    def test_display_config_to_dict_none(self):
        """Should return None for None input."""
        result = display_config_to_dict(None)
        assert result is None

    def test_display_config_to_dict_empty(self):
        """Should serialize empty display config with defaults."""
        config = ChartDisplayConfig()
        result = display_config_to_dict(config)

        assert result is not None
        assert result["title"] is None
        assert result["xLabel"] is None
        assert result["yLabel"] is None
        assert result["seriesLabels"] is None
        assert result["showLegend"] is True
        assert result["legendPosition"] is None
        assert result["metricFormat"] is None
        assert result["description"] is None
        assert result["gauge"] is None
        assert result["table"] is None

    def test_display_config_to_dict_full_chart(self):
        """Should serialize full chart display config with camelCase keys."""
        config = ChartDisplayConfig(
            title="Sales Dashboard",
            x_label="Date",
            y_label="Revenue ($)",
            series_labels={"daily_sales": "Daily Sales", "target": "Target"},
            show_legend=True,
            legend_position="top",
            description="Year-over-year comparison",
        )

        result = display_config_to_dict(config)

        assert result["title"] == "Sales Dashboard"
        assert result["xLabel"] == "Date"
        assert result["yLabel"] == "Revenue ($)"
        assert result["seriesLabels"] == {"daily_sales": "Daily Sales", "target": "Target"}
        assert result["showLegend"] is True
        assert result["legendPosition"] == "top"
        assert result["description"] == "Year-over-year comparison"

    def test_display_config_to_dict_metric(self):
        """Should serialize metric display config."""
        config = ChartDisplayConfig(
            title="Total Orders",
            metric_format="currency",
            description="All-time revenue",
        )

        result = display_config_to_dict(config)

        assert result["title"] == "Total Orders"
        assert result["metricFormat"] == "currency"
        assert result["description"] == "All-time revenue"
        assert result["xLabel"] is None
        assert result["yLabel"] is None

    def test_dict_to_display_config_none(self):
        """Should return None for None input."""
        result = dict_to_display_config(None)
        assert result is None

    def test_dict_to_display_config_empty(self):
        """Should deserialize empty dict to config with defaults."""
        result = dict_to_display_config({})

        assert result is not None
        assert result.title is None
        assert result.x_label is None
        assert result.y_label is None
        assert result.series_labels is None
        assert result.show_legend is True  # Default value
        assert result.legend_position is None
        assert result.metric_format is None
        assert result.description is None
        assert result.gauge is None
        assert result.table is None

    def test_dict_to_display_config_full_chart(self):
        """Should deserialize full chart config with snake_case fields."""
        data = {
            "title": "Sales Dashboard",
            "xLabel": "Date",
            "yLabel": "Revenue ($)",
            "seriesLabels": {"daily_sales": "Daily Sales"},
            "showLegend": False,
            "legendPosition": "bottom",
            "description": "Monthly trends",
        }

        result = dict_to_display_config(data)

        assert result.title == "Sales Dashboard"
        assert result.x_label == "Date"
        assert result.y_label == "Revenue ($)"
        assert result.series_labels == {"daily_sales": "Daily Sales"}
        assert result.show_legend is False
        assert result.legend_position == "bottom"
        assert result.description == "Monthly trends"

    def test_dict_to_display_config_metric(self):
        """Should deserialize metric config."""
        data = {
            "title": "Total Revenue",
            "metricFormat": "percent",
        }

        result = dict_to_display_config(data)

        assert result.title == "Total Revenue"
        assert result.metric_format == "percent"
        assert result.x_label is None
        assert result.y_label is None

    def test_roundtrip_serialization(self):
        """Should maintain data integrity through serialize -> deserialize."""
        original = ChartDisplayConfig(
            title="Test Chart",
            x_label="X Axis",
            y_label="Y Axis",
            series_labels={"col1": "Column 1", "col2": "Column 2"},
            show_legend=False,
            legend_position="right",
            metric_format="number",
            description="Test description",
            gauge=GaugeDisplayConfig(
                min_value=0,
                max_value=100,
                unit="%",
                thresholds=[(0.5, "#67e8f9"), (1.0, "#f87171")],
                start_angle=200,
                end_angle=-20,
                show_detail=True,
                show_axis_label=False,
            ),
            table=TableDisplayConfig(
                columns=[
                    TableColumnConfig(
                        field="revenue",
                        label="Revenue",
                        align="right",
                        format=TableValueFormat(format_type="currency", currency="USD"),
                    )
                ],
                default_format=TableValueFormat(format_type="number", precision=2),
                show_header=True,
                show_row_numbers=False,
                zebra_stripes=True,
                compact=False,
            ),
        )

        # Serialize to dict
        as_dict = display_config_to_dict(original)

        # Deserialize back to domain
        restored = dict_to_display_config(as_dict)

        assert restored == original

    def test_table_display_config_serialization(self):
        """Should serialize and deserialize table display config."""
        config = ChartDisplayConfig(
            table=TableDisplayConfig(
                columns=[
                    TableColumnConfig(
                        field="avg_latency",
                        label="Avg Latency",
                        align="right",
                        format=TableValueFormat(
                            format_type="number",
                            precision=3,
                            suffix=" ms",
                        ),
                    )
                ],
                default_format=TableValueFormat(null_display="-"),
                show_header=True,
                show_row_numbers=True,
                zebra_stripes=False,
                compact=True,
            )
        )

        as_dict = display_config_to_dict(config)
        restored = dict_to_display_config(as_dict)

        assert restored.table is not None
        assert restored.table.show_header is True
        assert restored.table.show_row_numbers is True
        assert restored.table.zebra_stripes is False
        assert restored.table.compact is True
        assert restored.table.default_format is not None
        assert restored.table.default_format.null_display == "-"
        assert restored.table.columns is not None
        assert restored.table.columns[0].field == "avg_latency"
        assert restored.table.columns[0].label == "Avg Latency"
        assert restored.table.columns[0].format is not None
        assert restored.table.columns[0].format.precision == 3

    def test_gauge_display_config_serialization(self):
        """Should serialize and deserialize gauge display config."""
        config = ChartDisplayConfig(
            gauge=GaugeDisplayConfig(
                min_value=10,
                max_value=200,
                unit="ms",
                thresholds=[(0.3, "#22c55e"), (0.7, "#f59e0b"), (1.0, "#ef4444")],
                start_angle=180,
                end_angle=0,
                show_detail=False,
                show_axis_label=True,
            )
        )

        as_dict = display_config_to_dict(config)
        restored = dict_to_display_config(as_dict)

        assert restored.gauge is not None
        assert restored.gauge.min_value == 10
        assert restored.gauge.max_value == 200
        assert restored.gauge.unit == "ms"
        assert restored.gauge.thresholds == [
            (0.3, "#22c55e"),
            (0.7, "#f59e0b"),
            (1.0, "#ef4444"),
        ]
        assert restored.gauge.start_angle == 180
        assert restored.gauge.end_angle == 0
        assert restored.gauge.show_detail is False
        assert restored.gauge.show_axis_label is True

    def test_partial_data_deserialization(self):
        """Should handle partial data gracefully."""
        data = {
            "title": "Partial Config",
            "xLabel": "X",
            # yLabel omitted
            # seriesLabels omitted
        }

        result = dict_to_display_config(data)

        assert result.title == "Partial Config"
        assert result.x_label == "X"
        assert result.y_label is None
        assert result.series_labels is None

    def test_unicode_serialization(self):
        """Should handle unicode characters correctly."""
        config = ChartDisplayConfig(
            title="销售趋势",
            x_label="日期",
            y_label="销售额（元）",
            series_labels={"sales": "每日销售"},
        )

        as_dict = display_config_to_dict(config)
        restored = dict_to_display_config(as_dict)

        assert restored.title == "销售趋势"
        assert restored.x_label == "日期"
        assert restored.series_labels["sales"] == "每日销售"

    def test_empty_series_labels(self):
        """Should handle empty series labels dict."""
        config = ChartDisplayConfig(series_labels={})

        as_dict = display_config_to_dict(config)
        restored = dict_to_display_config(as_dict)

        assert restored.series_labels == {}

    def test_show_legend_default_on_missing(self):
        """Should default showLegend to True when missing from dict."""
        data = {"title": "Test"}  # showLegend omitted

        result = dict_to_display_config(data)

        assert result.show_legend is True

    def test_show_legend_explicit_false(self):
        """Should respect explicit False for showLegend."""
        data = {"showLegend": False}

        result = dict_to_display_config(data)

        assert result.show_legend is False


class TestFilterConfigSerialization:
    """Test DashboardFilter fields persisted in config JSON."""

    def test_filter_required_and_time_precision_roundtrip(self):
        config = DashboardConfig(
            layout=DashboardLayout(),
            widgets=[],
            filters=[
                DashboardFilter(
                    id="filter-time",
                    name="Time",
                    type="time_range",
                    param_key="time",
                    value={"mode": "relative", "preset": "last_7_days"},
                    time_precision="date",
                    required=True,
                )
            ],
        )

        serialized = dashboard_config_to_dict(config)
        restored = dict_to_dashboard_config(serialized)

        assert serialized["filters"][0]["timePrecision"] == "date"
        assert serialized["filters"][0]["required"] is True
        assert restored.filters is not None
        assert restored.filters[0].time_precision == "date"
        assert restored.filters[0].required is True
