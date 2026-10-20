"""Smoke tests: each public chart type builds a Plotly figure."""

import json

import pytest

from apps.shared.chart import renderer
from apps.shared.chart.renderer import render_chart
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


@pytest.mark.parametrize(
    ("chart_type", "data", "kwargs", "min_traces"),
    [
        (
            "pie",
            [{"cat": "A", "val": 10}, {"cat": "B", "val": 20}],
            {"x_key": "cat", "y_key": "val"},
            1,
        ),
        (
            "area",
            [{"x": "Jan", "y": 1}, {"x": "Feb", "y": 2}],
            {"x_key": "x", "y_key": "y"},
            1,
        ),
        (
            "scatter",
            [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
            {"x_key": "x", "y_key": "y"},
            1,
        ),
        (
            "heatmap",
            [{"row": "R1", "col": "C1", "z": 5}],
            {"x_key": "col", "y_key": "row", "z_key": "z"},
            1,
        ),
        (
            "bar",
            [
                {"day": "Mon", "series": "S1", "v": 1},
                {"day": "Mon", "series": "S2", "v": 2},
            ],
            {"x_key": "day", "y_key": "v", "series_key": "series", "stacked": True},
            2,
        ),
    ],
)
def test_render_chart_type_builds_figure(capture_figure, chart_type, data, kwargs, min_traces):
    render_chart(
        chart_type=chart_type,
        data=json.dumps(data),
        title=f"Test {chart_type}",
        **kwargs,
    )
    fig = capture_figure["fig"]
    assert len(fig.data) >= min_traces
