"""Data processor pivot and duplicate-x helpers."""

import pytest

from apps.shared.chart.data_processor import handle_duplicate_x_values, pivot_long_to_wide


def test_handle_duplicate_x_values_appends_indices():
    assert handle_duplicate_x_values(["A", "B", "A"]) == ["A (1)", "B", "A (2)"]


def test_handle_duplicate_x_values_unchanged_when_unique():
    assert handle_duplicate_x_values(["X", "Y"]) == ["X", "Y"]


def test_pivot_long_to_wide_passthrough_when_columns_exist():
    rows = [{"month": "Jan", "a": 1, "b": 2}]
    out = pivot_long_to_wide(rows, "month", ["a", "b"])
    assert out == rows


def test_pivot_long_to_wide_from_long_format():
    rows = [
        {"month": "Jan", "product": "A", "sales": 10},
        {"month": "Jan", "product": "B", "sales": 8},
        {"month": "Feb", "product": "A", "sales": 12},
    ]
    out = pivot_long_to_wide(rows, "month", ["A", "B"], value_col="sales")
    assert out == [
        {"month": "Jan", "A": 10, "B": 8},
        {"month": "Feb", "A": 12, "B": 0},
    ]


def test_pivot_long_to_wide_raises_when_series_unknown():
    rows = [{"month": "Jan", "product": "A", "sales": 1}]
    with pytest.raises(ValueError, match="Cannot find a column"):
        pivot_long_to_wide(rows, "month", ["X", "Y"])
