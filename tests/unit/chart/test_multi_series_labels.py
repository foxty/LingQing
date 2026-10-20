"""Multi-series Y-axis labels and wide-format series_key errors."""

import json

import pytest

from apps.shared.chart import renderer
from apps.shared.chart.renderer import _resolve_multi_series_y_label, render_chart
from apps.shared.chart.types import ChartRenderResult


def test_resolve_multi_series_y_label_prefers_y_label():
    assert _resolve_multi_series_y_label("Order Intake (USD)", "amt", ["this_year", "last_year"]) == "Order Intake (USD)"


def test_resolve_multi_series_y_label_uses_y_key_when_not_series_column():
    assert _resolve_multi_series_y_label(None, "amt", ["this_year", "last_year"]) == "amt"


def test_resolve_multi_series_y_label_default_value():
    assert _resolve_multi_series_y_label(None, None, ["this_year", "last_year"]) == "Value"


def test_series_key_on_wide_data_suggests_series_keys(monkeypatch):
    captured: dict = {}

    def _capture(fig, title: str) -> ChartRenderResult:
        captured["fig"] = fig
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=b"\x89PNG\r\n\x1a\n", title=title)

    monkeypatch.setattr(renderer, "_plotly_figure_to_result", _capture)

    data = json.dumps([{"d": "2026-09-21", "this_year": 100, "last_year": 90}])
    with pytest.raises(ValueError, match="WIDE-format"):
        render_chart(
            chart_type="line",
            data=data,
            title="YoY",
            x_key="d",
            y_key="amt",
            series_key="series",
        )


def test_wide_multi_line_y_axis_uses_y_key_not_first_series(monkeypatch):
    captured: dict = {}

    def _capture(fig, title: str) -> ChartRenderResult:
        captured["fig"] = fig
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=b"\x89PNG\r\n\x1a\n", title=title)

    monkeypatch.setattr(renderer, "_plotly_figure_to_result", _capture)

    data = json.dumps([{"d": "2026-09-21", "this_year": 100, "last_year": 90}])
    render_chart(
        chart_type="line",
        data=data,
        title="YoY",
        x_key="d",
        y_key="amt",
        series_keys=["this_year", "last_year"],
    )
    y_title = captured["fig"].layout.yaxis.title.text
    assert "this_year" not in y_title
    assert "amt" in y_title
