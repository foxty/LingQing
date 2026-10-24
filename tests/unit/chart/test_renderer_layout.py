"""Unit tests for Plotly layout helpers wired in chart renderer."""

import json

import pytest

from apps.shared.chart import renderer
from apps.shared.chart.data_processor import infer_axis_tickformat
from apps.shared.chart.renderer import _build_title_layout, render_chart
from apps.shared.chart.types import ChartRenderResult


@pytest.fixture
def capture_figure(monkeypatch):
    captured: dict = {}

    def _capture(fig, title: str) -> ChartRenderResult:
        captured["fig"] = fig
        captured["title"] = title
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=b"\x89PNG\r\n\x1a\n", title=title)

    monkeypatch.setattr(renderer, "_plotly_figure_to_result", _capture)
    return captured


def test_build_title_layout_wraps_long_title_and_reserves_legend_margin():
    title = "Order Intake by Country — Last Week vs Prior Week (WoW)"
    layout, top_margin = _build_title_layout(title, has_legend=True)

    assert "<br>" in layout["text"]
    assert layout["font"]["size"] <= 18
    assert top_margin >= 144


def test_build_title_layout_short_title_unchanged():
    layout, top_margin = _build_title_layout("Monthly Sales")
    assert layout["text"] == "<b>Monthly Sales</b>"
    assert top_margin == 100


def test_infer_axis_tickformat_scales_with_magnitude():
    assert infer_axis_tickformat([1.5, 2.3]) == ",.2f"
    assert infer_axis_tickformat([1500.0, 3200.0]) == ",.1f"
    assert infer_axis_tickformat([25_000.0, 80_000.0]) == ",.0f"
    assert infer_axis_tickformat([2_500_000.0]) == "~s"


def test_render_bar_yaxis_uses_magnitude_tickformat(capture_figure):
    render_chart(
        chart_type="bar",
        data=json.dumps([{"region": "North", "sales": 1_250_000}, {"region": "South", "sales": 980_000}]),
        title="Regional sales",
        x_key="region",
        y_key="sales",
    )
    assert capture_figure["fig"].layout.yaxis.tickformat == "~s"


def test_render_bar_partial_dates_use_category_xaxis(capture_figure):
    render_chart(
        chart_type="bar",
        data=json.dumps([{"day": "09-16", "sales": 100}, {"day": "10-01", "sales": 120}]),
        title="Partial dates",
        x_key="day",
        y_key="sales",
    )
    assert capture_figure["fig"].layout.xaxis.type == "category"


def test_render_line_full_dates_use_date_xaxis(capture_figure):
    render_chart(
        chart_type="line",
        data=json.dumps(
            [
                {"day": "2026-09-16", "value": 100},
                {"day": "2026-09-17", "value": 150},
            ]
        ),
        title="Full dates",
        x_key="day",
        y_key="value",
    )
    assert capture_figure["fig"].layout.xaxis.type == "date"


def test_render_grouped_bar_partial_dates_use_category_xaxis(capture_figure):
    render_chart(
        chart_type="bar",
        data=json.dumps(
            [
                {"day": "09-16", "series": "Last Week", "value": 100},
                {"day": "09-16", "series": "Prior Week", "value": 80},
                {"day": "10-01", "series": "Last Week", "value": 120},
                {"day": "10-01", "series": "Prior Week", "value": 90},
            ]
        ),
        title="WoW",
        x_key="day",
        y_key="value",
        series_key="series",
    )
    fig = capture_figure["fig"]
    assert fig.layout.xaxis.type == "category"
    assert fig.layout.width == 960
