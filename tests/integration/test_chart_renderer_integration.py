"""Integration tests for chart renderer (SVG generation with kaleido)."""

from unittest.mock import patch

import pytest

from apps.shared.chart.renderer import render_chart


@pytest.fixture
def charts_tmp_path(tmp_path):
    """Provide a temporary directory for chart output."""
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    return charts_dir


class TestRenderChartSVGGeneration:
    """Test that render_chart actually generates SVG files via kaleido."""

    def test_render_bar_chart_creates_svg(self, charts_tmp_path):
        """Bar chart should produce a valid SVG file."""
        data = '[{"month":"Jan","sales":100},{"month":"Feb","sales":120},{"month":"Mar","sales":80}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="bar",
                    data=data,
                    title="Monthly Sales",
                    x_key="month",
                    y_key="sales",
                )

        # Verify markdown output
        assert "![Monthly Sales]" in result
        assert result.endswith("\n\n")

        # Verify SVG file was created
        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

        # Verify SVG content
        svg_content = svg_files[0].read_text(encoding="utf-8")
        assert svg_content.startswith("<?xml") or svg_content.startswith("<svg")
        assert "Monthly Sales" in svg_content

    def test_render_line_chart_creates_svg(self, charts_tmp_path):
        """Line chart should produce a valid SVG file."""
        data = '[{"date":"2024-01","value":100},{"date":"2024-02","value":150},{"date":"2024-03","value":120}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="line",
                    data=data,
                    title="Trend",
                    x_key="date",
                    y_key="value",
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

        svg_content = svg_files[0].read_text(encoding="utf-8")
        assert "<svg" in svg_content

    def test_render_pie_chart_creates_svg(self, charts_tmp_path):
        """Pie chart should produce a valid SVG file."""
        data = '[{"product":"A","qty":50},{"product":"B","qty":30},{"product":"C","qty":20}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="pie",
                    data=data,
                    title="Product Distribution",
                    x_key="product",
                    y_key="qty",
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_scatter_chart_creates_svg(self, charts_tmp_path):
        """Scatter chart should produce a valid SVG file."""
        data = '[{"x":1,"y":10},{"x":2,"y":20},{"x":3,"y":15}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="scatter",
                    data=data,
                    title="X vs Y",
                    x_key="x",
                    y_key="y",
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_multi_series_bar_creates_svg(self, charts_tmp_path):
        """Multi-series bar chart with series_keys should produce a valid SVG file."""
        data = '[{"month":"Jan","A":100,"B":80},{"month":"Feb","A":120,"B":90},{"month":"Mar","A":80,"B":110}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="bar",
                    data=data,
                    title="Sales by Product",
                    x_key="month",
                    y_key="sales",
                    series_keys=["A", "B"],
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_multi_series_line_creates_svg(self, charts_tmp_path):
        """Multi-series line chart with series_keys should produce a valid SVG file."""
        data = '[{"month":"Jan","west":100,"east":80},{"month":"Feb","west":120,"east":90}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="line",
                    data=data,
                    title="Regional Trend",
                    x_key="month",
                    y_key="value",
                    series_keys=["west", "east"],
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_area_chart_creates_svg(self, charts_tmp_path):
        """Area chart should produce a valid SVG file."""
        data = '[{"month":"Jan","visits":100},{"month":"Feb","visits":150},{"month":"Mar","visits":120}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="area",
                    data=data,
                    title="Visits Over Time",
                    x_key="month",
                    y_key="visits",
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_heatmap_creates_svg(self, charts_tmp_path):
        """Heatmap should produce a valid SVG file."""
        data = (
            '[{"weekday":"Mon","hour":"9am","cnt":10},'
            '{"weekday":"Mon","hour":"10am","cnt":20},'
            '{"weekday":"Tue","hour":"9am","cnt":15},'
            '{"weekday":"Tue","hour":"10am","cnt":25}]'
        )

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="heatmap",
                    data=data,
                    title="Traffic Heatmap",
                    x_key="hour",
                    y_key="weekday",
                    z_key="cnt",
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_scatter_with_series_key_creates_svg(self, charts_tmp_path):
        """Scatter with series_key (categorical coloring) should produce a valid SVG file."""
        data = (
            '[{"price":10,"qty":5,"cat":"A"},'
            '{"price":20,"qty":8,"cat":"B"},'
            '{"price":15,"qty":6,"cat":"A"},'
            '{"price":25,"qty":10,"cat":"B"}]'
        )

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="scatter",
                    data=data,
                    title="Price vs Qty by Category",
                    x_key="price",
                    y_key="qty",
                    series_key="cat",
                )

        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 1

    def test_render_chart_url_includes_filename(self, charts_tmp_path):
        """Returned URL should contain the SVG filename."""
        data = '[{"x":"a","y":1}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
                mock_config.CHART_SERVICE_URL = "http://localhost:8000"
                result = render_chart(
                    chart_type="bar",
                    data=data,
                    title="Test Chart",
                    x_key="x",
                    y_key="y",
                )

        # URL should be in markdown format
        assert "http://localhost:8000/static/charts/chart_" in result
        assert ".svg" in result

    def test_render_empty_data_returns_error(self, charts_tmp_path):
        """Empty data should return an error message."""
        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            result = render_chart(
                chart_type="bar",
                data="[]",
                title="Empty",
            )

        assert "Error: No data provided" in result
        # No SVG file should be created
        svg_files = list(charts_tmp_path.glob("chart_*.svg"))
        assert len(svg_files) == 0

    def test_render_invalid_chart_type_raises(self, charts_tmp_path):
        """Invalid chart type should raise ValueError."""
        data = '[{"x":"a","y":1}]'

        with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
            with pytest.raises(ValueError, match="Unknown chart_type"):
                render_chart(
                    chart_type="invalid_type",
                    data=data,
                    title="Bad",
                    x_key="x",
                    y_key="y",
                )
