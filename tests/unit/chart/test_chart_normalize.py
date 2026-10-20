"""Unit tests for Plotly chart_type normalization."""

import pytest

from apps.shared.chart.normalize import normalize_plotly_chart_type


def test_normalize_bar_with_series_becomes_grouped_or_stacked():
    assert normalize_plotly_chart_type("bar", ["A", "B"], stacked=False) == "grouped_bar"
    assert normalize_plotly_chart_type("bar", ["A", "B"], stacked=True) == "stacked_bar"


def test_normalize_line_with_series_becomes_multi_line():
    assert normalize_plotly_chart_type("line", ["A"], stacked=False) == "multi_line"


def test_normalize_explicit_plotly_types_pass_through():
    assert normalize_plotly_chart_type("stacked_bar", ["A"], stacked=False) == "stacked_bar"


def test_normalize_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unknown chart_type"):
        normalize_plotly_chart_type("gauge", None, stacked=False)
