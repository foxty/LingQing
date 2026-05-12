"""Unit tests for dashboard tool helper functions."""

from apps.shared.dashboard.domain import FieldMapping
from apps.shared.dashboard.service import (
    _infer_label_from_column_name,
    _infer_series_labels_from_field_mapping,
)


class TestInferLabelFromColumnName:
    """Test column name to label inference."""

    def test_snake_case(self):
        """Should convert snake_case to Title Case."""
        assert _infer_label_from_column_name("daily_sales") == "Daily Sales"
        assert _infer_label_from_column_name("total_revenue") == "Total Revenue"
        assert _infer_label_from_column_name("order_count") == "Order Count"

    def test_single_word(self):
        """Should capitalize single word."""
        assert _infer_label_from_column_name("sales") == "Sales"
        assert _infer_label_from_column_name("revenue") == "Revenue"

    def test_camel_case(self):
        """Should insert spaces for camelCase."""
        assert _infer_label_from_column_name("dailySales") == "Daily Sales"
        assert _infer_label_from_column_name("totalRevenue") == "Total Revenue"
        assert _infer_label_from_column_name("orderCount") == "Order Count"

    def test_mixed_case(self):
        """Should handle mixed snake_case and camelCase."""
        assert _infer_label_from_column_name("total_revenueUSD") == "Total Revenue Usd"

    def test_all_caps(self):
        """Should handle all caps."""
        assert _infer_label_from_column_name("USD") == "Usd"
        assert _infer_label_from_column_name("API") == "Api"

    def test_empty_string(self):
        """Should return empty string for empty input."""
        assert _infer_label_from_column_name("") == ""

    def test_with_numbers(self):
        """Should handle numbers in column names."""
        assert _infer_label_from_column_name("sales_q1") == "Sales Q1"
        assert _infer_label_from_column_name("revenue_2024") == "Revenue 2024"

    def test_multiple_underscores(self):
        """Should handle multiple consecutive underscores."""
        assert _infer_label_from_column_name("total__sales") == "Total  Sales"

    def test_unicode_characters(self):
        """Should handle unicode characters."""
        # Unicode should pass through unchanged
        label = _infer_label_from_column_name("销售额")
        assert label == "销售额"


class TestInferSeriesLabelsFromFieldMapping:
    """Test series labels inference from field mapping."""

    def test_none_field_mapping(self):
        """Should return None for None input."""
        result = _infer_series_labels_from_field_mapping(None)
        assert result is None

    def test_no_series(self):
        """Should return None when no series defined."""
        mapping = FieldMapping(x_axis="date")
        result = _infer_series_labels_from_field_mapping(mapping)
        assert result is None

    def test_empty_series_list(self):
        """Should return None for empty series list."""
        mapping = FieldMapping(series=[])
        result = _infer_series_labels_from_field_mapping(mapping)
        assert result is None

    def test_single_series_string(self):
        """Should infer label for single series."""
        mapping = FieldMapping(series=["daily_sales"])
        result = _infer_series_labels_from_field_mapping(mapping)

        assert result == {"daily_sales": "Daily Sales"}

    def test_multiple_series_strings(self):
        """Should infer labels for multiple series."""
        mapping = FieldMapping(series=["daily_sales", "total_revenue", "orderCount"])
        result = _infer_series_labels_from_field_mapping(mapping)

        assert result == {
            "daily_sales": "Daily Sales",
            "total_revenue": "Total Revenue",
            "orderCount": "Order Count",
        }

    def test_series_with_dict_format(self):
        """Should handle series as list of dicts with 'name' field."""
        mapping = FieldMapping(
            series=[
                {"name": "daily_sales", "type": "line"},
                {"name": "total_revenue", "type": "bar"},
            ]
        )
        result = _infer_series_labels_from_field_mapping(mapping)

        assert result == {
            "daily_sales": "Daily Sales",
            "total_revenue": "Total Revenue",
        }

    def test_mixed_series_format(self):
        """Should handle mix of strings and dicts."""
        mapping = FieldMapping(
            series=[
                "sales",
                {"name": "revenue"},
            ]
        )
        result = _infer_series_labels_from_field_mapping(mapping)

        assert result == {
            "sales": "Sales",
            "revenue": "Revenue",
        }

    def test_series_with_special_names(self):
        """Should handle special column names."""
        mapping = FieldMapping(series=["_id", "col__name", "CamelCase"])
        result = _infer_series_labels_from_field_mapping(mapping)

        assert result is not None
        assert "_id" in result
        assert "col__name" in result
        assert "CamelCase" in result
