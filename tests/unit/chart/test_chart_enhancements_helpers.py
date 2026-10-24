"""Unit tests for chart enhancement helpers."""


import plotly.graph_objects as go
import pytest

from apps.shared.chart.data_processor import infer_percent_tickformat
from apps.shared.chart.enhancements import apply_chart_enhancements, parse_json_list


def test_infer_percent_tickformat_fraction_vs_whole():
    assert infer_percent_tickformat([0.12, 0.85]) == ".0%"
    assert infer_percent_tickformat([12.5, 85.0]) == ".1f"


def test_parse_json_list_empty_and_valid():
    assert parse_json_list(None, field_name="reference_lines_json") == []
    assert parse_json_list("  ", field_name="reference_lines_json") == []
    parsed = parse_json_list('[{"y": 1}]', field_name="reference_lines_json")
    assert parsed == [{"y": 1}]


def test_parse_json_list_rejects_non_array():
    with pytest.raises(ValueError, match="reference_lines_json must be a JSON array"):
        parse_json_list('{"y": 1}', field_name="reference_lines_json")


def test_apply_chart_enhancements_annotations_and_percent_axis():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[0.1, 0.2])])
    apply_chart_enhancements(
        fig,
        subtitle=None,
        reference_lines=None,
        annotations=[{"text": "Peak", "x": 2, "y": 0.2, "showarrow": False}],
        y_axis_percent=True,
        y_numeric_samples=[0.1, 0.2],
    )
    assert fig.layout.yaxis.tickformat == ".0%"
    assert len(fig.layout.annotations or ()) >= 1
