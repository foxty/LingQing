"""Integration tests for chart renderer (SVG generation with kaleido)."""

import pytest

from apps.shared.chart.renderer import render_chart


class TestRenderChartSVGGeneration:
    """Test that render_chart returns valid SVG and PNG bytes via kaleido."""

    def test_render_bar_chart_cjk_labels_in_svg(self):
        title = "亚太地区销售额"
        data = '[{"region":"中国","sales":1250},{"region":"한국","sales":980}]'
        result = render_chart(
            chart_type="bar",
            data=data,
            title=title,
            x_key="region",
            y_key="sales",
            x_label="地区",
            y_label="销售额 (USD)",
        )
        svg_content = result.svg_bytes.decode("utf-8")
        assert title in svg_content
        assert "中国" in svg_content

    def test_render_bar_chart_returns_bytes(self):
        data = '[{"month":"Jan","sales":100},{"month":"Feb","sales":120},{"month":"Mar","sales":80}]'
        result = render_chart(
            chart_type="bar",
            data=data,
            title="Monthly Sales",
            x_key="month",
            y_key="sales",
        )
        assert result.title == "Monthly Sales"
        svg_content = result.svg_bytes.decode("utf-8")
        assert svg_content.startswith("<?xml") or svg_content.startswith("<svg")
        assert "Monthly Sales" in svg_content
        assert result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    def test_render_line_chart_returns_bytes(self):
        data = '[{"date":"2024-01","value":100},{"date":"2024-02","value":150}]'
        result = render_chart(
            chart_type="line",
            data=data,
            title="Trend",
            x_key="date",
            y_key="value",
        )
        assert b"<svg" in result.svg_bytes

    def test_render_long_title_visible_in_svg(self):
        title = "Order Intake by Country — Last Week vs Prior Week (WoW)"
        data = '[{"country":"US","sales":100},{"country":"CN","sales":200}]'
        result = render_chart(
            chart_type="bar",
            data=data,
            title=title,
            x_key="country",
            y_key="sales",
        )
        svg_content = result.svg_bytes.decode("utf-8")
        assert "Order Intake" in svg_content
        assert "Prior Week" in svg_content

    def test_render_empty_data_raises(self):
        with pytest.raises(ValueError, match="No data provided"):
            render_chart(chart_type="bar", data="[]", title="Empty")

    def test_render_invalid_chart_type_raises(self):
        data = '[{"x":"a","y":1}]'
        with pytest.raises(ValueError, match="Unknown chart_type"):
            render_chart(
                chart_type="invalid_type",
                data=data,
                title="Bad",
                x_key="x",
                y_key="y",
            )

    def test_render_waterfall_returns_bytes(self):
        data = (
            '[{"step":"Start","amount":100,"kind":"absolute"},'
            '{"step":"Add","amount":20,"kind":"relative"}]'
        )
        result = render_chart(
            chart_type="waterfall",
            data=data,
            title="Bridge",
            x_key="step",
            y_key="amount",
            measure_key="kind",
        )
        assert result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        svg_content = result.svg_bytes.decode("utf-8")
        assert "Bridge" in svg_content
