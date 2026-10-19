"""Unit tests for Plotly x-axis type inference."""

from apps.shared.chart.data_processor import is_full_calendar_date, plotly_xaxis_type_kwargs


def test_is_full_calendar_date_accepts_iso_and_datetime():
    assert is_full_calendar_date("2026-09-16")
    assert is_full_calendar_date("2026-09-16 00:00:00")
    assert is_full_calendar_date("2026-09-16T12:30:00Z")


def test_is_full_calendar_date_rejects_partial_dates():
    assert not is_full_calendar_date("09-16")
    assert not is_full_calendar_date("2024-01")
    assert not is_full_calendar_date("Jan")


def test_plotly_xaxis_type_all_full_dates_uses_date_axis():
    assert plotly_xaxis_type_kwargs(["2026-09-16", "2026-09-17"]) == {"type": "date"}


def test_plotly_xaxis_type_partial_dates_use_category():
    assert plotly_xaxis_type_kwargs(["09-16", "10-01"]) == {"type": "category"}
    assert plotly_xaxis_type_kwargs(["Australia", "China"]) == {"type": "category"}


def test_plotly_xaxis_type_numeric_uses_default_linear():
    assert plotly_xaxis_type_kwargs([1, 2, 3]) == {}


def test_plotly_xaxis_type_mixed_full_and_partial_uses_category():
    assert plotly_xaxis_type_kwargs(["2026-09-16", "09-17"]) == {"type": "category"}
