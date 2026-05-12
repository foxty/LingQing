from apps.shared.chart.data_processor import (
    coerce_numeric_value as _coerce_numeric_value,
)
from apps.shared.chart.data_processor import (
    ensure_numeric_series as _ensure_numeric_series,
)
from apps.shared.chart.data_processor import (
    format_value_labels as _format_value_labels,
)


def test_coerce_numeric_value_accepts_numeric_strings():
    assert _coerce_numeric_value("123") == 123.0
    assert _coerce_numeric_value("1,234.50") == 1234.5


def test_format_value_labels_handles_mixed_numeric_input():
    labels = _format_value_labels([100, "200", 3.5])
    assert labels == ["100", "200", "3.50"]


def test_ensure_numeric_series_raises_on_non_numeric_value():
    try:
        _ensure_numeric_series(["100", "abc"], chart_type="bar", field_name="value")
        assert False, "Expected ValueError for non-numeric series value"
    except ValueError as exc:
        assert "requires numeric" in str(exc)
        assert "abc" in str(exc)
