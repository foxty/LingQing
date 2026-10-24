"""Report chart enhancements and new chart types."""

import json

import pytest

from apps.shared.chart import grid as grid_mod
from apps.shared.chart import renderer
from apps.shared.chart.grid import render_chart_grid
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
    monkeypatch.setattr(grid_mod, "_plotly_figure_to_result", _capture)
    return captured


def test_render_horizontal_bar(capture_figure):
    render_chart(
        chart_type="horizontal_bar",
        data=json.dumps([{"region": "North", "sales": 100}, {"region": "South", "sales": 80}]),
        title="Sales",
        x_key="region",
        y_key="sales",
    )
    trace = capture_figure["fig"].data[0]
    assert trace.orientation == "h"


def test_render_waterfall(capture_figure):
    render_chart(
        chart_type="waterfall",
        data=json.dumps(
            [
                {"step": "Start", "amount": 100, "kind": "absolute"},
                {"step": "Add", "amount": 20, "kind": "relative"},
                {"step": "Total", "amount": 0, "kind": "total"},
            ]
        ),
        title="Bridge",
        x_key="step",
        y_key="amount",
        measure_key="kind",
    )
    assert capture_figure["fig"].data[0].type == "waterfall"


def test_render_waterfall_infers_total_on_last_step(capture_figure):
    render_chart(
        chart_type="waterfall",
        data=json.dumps(
            [
                {"step": "Start", "amount": 100},
                {"step": "Delta", "amount": -10},
                {"step": "Total", "amount": 90},
            ]
        ),
        title="Bridge",
        x_key="step",
        y_key="amount",
    )
    measures = list(capture_figure["fig"].data[0].measure)
    assert measures[-1] == "total"
    assert measures[0] == "relative"


def test_render_violin_by_group(capture_figure):
    render_chart(
        chart_type="violin",
        data=json.dumps(
            [
                {"g": "A", "v": 1},
                {"g": "A", "v": 3},
                {"g": "B", "v": 5},
            ]
        ),
        title="Violin",
        x_key="g",
        y_key="v",
    )
    assert capture_figure["fig"].data[0].type == "violin"
    assert len(capture_figure["fig"].data) == 2


def test_render_box_single_distribution_without_x_key(capture_figure):
    render_chart(
        chart_type="box",
        data=json.dumps([{"score": 10}, {"score": 20}, {"score": 15}]),
        title="Scores",
        y_key="score",
    )
    assert len(capture_figure["fig"].data) == 1


def test_render_box_by_group(capture_figure):
    render_chart(
        chart_type="box",
        data=json.dumps(
            [
                {"g": "A", "v": 1},
                {"g": "A", "v": 3},
                {"g": "B", "v": 5},
            ]
        ),
        title="Distribution",
        x_key="g",
        y_key="v",
    )
    assert len(capture_figure["fig"].data) == 2


def test_reference_line_and_subtitle(capture_figure):
    render_chart(
        chart_type="line",
        data=json.dumps([{"m": "Jan", "v": 10}, {"m": "Feb", "v": 20}]),
        title="Trend",
        x_key="m",
        y_key="v",
        subtitle="FY2026",
        reference_lines_json='[{"y": 15, "label": "Target"}]',
    )
    fig = capture_figure["fig"]
    assert "FY2026" in (fig.layout.title.text or "")
    assert len(fig.layout.shapes or []) >= 1


def test_y_axis_percent_tickformat(capture_figure):
    render_chart(
        chart_type="bar",
        data=json.dumps([{"m": "A", "rate": 0.25}, {"m": "B", "rate": 0.5}]),
        title="Rates",
        x_key="m",
        y_key="rate",
        y_axis_percent=True,
    )
    assert capture_figure["fig"].layout.yaxis.tickformat == ".0%"


def test_annotations_json_on_chart(capture_figure):
    render_chart(
        chart_type="line",
        data=json.dumps([{"m": "Jan", "v": 10}, {"m": "Feb", "v": 20}]),
        title="Trend",
        x_key="m",
        y_key="v",
        annotations_json='[{"text": "+100%", "x": "Feb", "y": 20, "showarrow": true}]',
    )
    assert len(capture_figure["fig"].layout.annotations or ()) >= 1


def test_scatter_applies_reference_lines(capture_figure):
    render_chart(
        chart_type="scatter",
        data=json.dumps([{"x": 1, "y": 2}, {"x": 3, "y": 5}]),
        title="Scatter",
        x_key="x",
        y_key="y",
        reference_lines_json='[{"y": 4, "label": "Avg"}]',
    )
    assert len(capture_figure["fig"].layout.shapes or []) >= 1


def test_render_chart_grid(capture_figure):
    panels = json.dumps(
        [
            {"chart_type": "bar", "title": "A", "x_key": "m", "y_key": "a", "row": 1, "col": 1},
            {"chart_type": "line", "title": "B", "x_key": "m", "y_key": "b", "row": 1, "col": 2},
        ]
    )
    data = json.dumps([{"m": "Jan", "a": 1, "b": 2}])
    result = render_chart_grid(data=data, title="Grid", panels=panels, rows=1, cols=2)
    assert result.title == "Grid"
    assert len(capture_figure["fig"].data) == 2


def test_render_chart_grid_horizontal_bar_and_pie_panels(capture_figure):
    panels = json.dumps(
        [
            {"chart_type": "horizontal_bar", "title": "H", "x_key": "m", "y_key": "a", "row": 1, "col": 1},
            {"chart_type": "pie", "title": "P", "x_key": "m", "y_key": "b", "row": 1, "col": 2},
        ]
    )
    data = json.dumps([{"m": "Jan", "a": 1, "b": 2}, {"m": "Feb", "a": 3, "b": 4}])
    render_chart_grid(data=data, title="Mixed", panels=panels, rows=1, cols=2)
    traces = capture_figure["fig"].data
    assert traces[0].orientation == "h"
    assert traces[1].type == "pie"


def test_render_chart_grid_subtitle(capture_figure):
    panels = json.dumps([{"chart_type": "bar", "x_key": "m", "y_key": "a", "row": 1, "col": 1}])
    data = json.dumps([{"m": "Jan", "a": 1}])
    render_chart_grid(data=data, title="Grid", panels=panels, rows=1, cols=1, subtitle="Q1")
    assert "Q1" in (capture_figure["fig"].layout.title.text or "")


@pytest.mark.parametrize(
    ("panels", "rows", "cols", "match"),
    [
        ("[]", 2, 2, "panels must be a non-empty"),
        ('[{"chart_type": "gauge", "x_key": "m", "y_key": "a", "row": 1, "col": 1}]', 1, 1, "not supported in grid"),
        (
            '[{"chart_type": "bar", "x_key": "m", "y_key": "a", "row": 1, "col": 1},'
            '{"chart_type": "bar", "x_key": "m", "y_key": "a", "row": 1, "col": 2},'
            '{"chart_type": "bar", "x_key": "m", "y_key": "a", "row": 2, "col": 1}]',
            1,
            1,
            "At most 1 panels",
        ),
        ('[{"chart_type": "bar", "y_key": "a", "row": 1, "col": 1}]', 1, 1, "requires x_key and y_key"),
    ],
)
def test_render_chart_grid_validation_errors(panels, rows, cols, match):
    data = json.dumps([{"m": "Jan", "a": 1}])
    with pytest.raises(ValueError, match=match):
        render_chart_grid(data=data, title="Bad", panels=panels, rows=rows, cols=cols)
