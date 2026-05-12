"""Pure data processing utilities for chart rendering.

Extracted from the agent chart tool so they can be shared by the Plotly SVG
renderer, future export pipelines, and tests without importing Plotly.
"""

from numbers import Number
from typing import Any, Dict, List


def coerce_numeric_value(value: Any) -> float | None:
    """Convert raw value to float when possible.

    Accepts ints/floats and numeric strings (including comma-separated values).
    Returns None when conversion is not possible.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return float(value)

    if isinstance(value, Number):
        return float(value)

    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    return None


def ensure_numeric_series(values: List[Any], chart_type: str, field_name: str) -> List[float]:
    """Ensure a series contains numeric values for plotting and formatting.

    Raises ValueError with chart type and position context when a non-numeric
    value is encountered.
    """
    numeric_values: List[float] = []
    for idx, value in enumerate(values):
        numeric = coerce_numeric_value(value)
        if numeric is None:
            raise ValueError(
                f"Chart '{chart_type}' requires numeric {field_name}; got non-numeric value at index {idx}: {value!r}"
            )
        numeric_values.append(numeric)
    return numeric_values


def format_value_label(value: Any) -> str:
    """Format a single value as a human-readable label for chart data points."""
    numeric = coerce_numeric_value(value)
    if numeric is None:
        return str(value)
    if numeric.is_integer():
        return f"{numeric:,.0f}"
    return f"{numeric:,.2f}"


def format_value_labels(values: List[Any]) -> List[str]:
    """Format a value series into human-readable labels."""
    return [format_value_label(v) for v in values]


def handle_duplicate_x_values(x_values: List[Any]) -> List[Any]:
    """Handle duplicate x-axis values by appending indices to make them unique.

    Examples:
        ["A", "B", "A"] -> ["A (1)", "B", "A (2)"]
        ["X", "Y", "Z"] -> ["X", "Y", "Z"] (no duplicates, unchanged)
    """
    seen = {}
    result = []

    for val in x_values:
        if val in seen:
            seen[val] += 1
            result.append(f"{val} ({seen[val]})")
        else:
            seen[val] = 1
            if x_values.count(val) > 1:
                result.append(f"{val} (1)")
            else:
                result.append(val)

    return result


def pivot_long_to_wide(
    data_list: List[Dict[str, Any]],
    x_key: str,
    series_keys: List[str],
    value_col: str | None = None,
) -> List[Dict[str, Any]]:
    """Auto-pivot long-format data to wide format for multi-series charts.

    When series_keys are values inside a column (long format) rather than
    column names (wide format), detects the pivot column and value column
    and reshapes the data.

    Long:  [{col_range: "1-10", platform: "hive", table_count: 50}, ...]
    Wide:  [{col_range: "1-10", hive: 50, snowflake: 20}, ...]

    Args:
        data_list: List of row dicts.
        x_key: Column used as the x-axis key.
        series_keys: Series names — either column names (wide) or values in a
            pivot column (long). Wide format is returned unchanged.
        value_col: Explicit numeric value column to pivot (overrides auto-detection).
    """
    if not data_list:
        return data_list

    columns = list(data_list[0].keys())

    # Already wide format — all series_keys exist as column names.
    if all(sk in columns for sk in series_keys):
        return data_list

    # Find the column whose unique values contain ALL series_key values.
    series_values_set = set(series_keys)
    series_col = None
    for col in columns:
        if col == x_key:
            continue
        col_values = {str(row[col]) for row in data_list}
        if series_values_set.issubset(col_values):
            series_col = col
            break

    if series_col is None:
        raise ValueError(
            f"Cannot find a column whose values contain all series_keys {series_keys}. "
            f"Available columns: {columns}. "
            f"For multi-series charts, SQL must return WIDE FORMAT (each series as a separate column) "
            f"OR the series_keys must match values in a single pivot column."
        )

    # Find the value column.
    if value_col and value_col not in (x_key, series_col):
        detected_value_col = value_col
    else:
        detected_value_col = None
        for col in columns:
            if col in (x_key, series_col):
                continue
            if coerce_numeric_value(data_list[0].get(col)) is not None:
                detected_value_col = col
                break

    if detected_value_col is None:
        raise ValueError(
            f"Cannot find a numeric value column to pivot. "
            f"Columns: {columns}, x_key={x_key!r}, series_col={series_col!r}"
        )

    # Pivot: group by x_key, spread series_col values into wide columns.
    wide_rows: Dict[Any, Dict[str, Any]] = {}
    x_order: List[Any] = []
    for row in data_list:
        x_val = row[x_key]
        if x_val not in wide_rows:
            wide_rows[x_val] = {x_key: x_val}
            x_order.append(x_val)
        series_val = str(row[series_col])
        if series_val in series_values_set:
            wide_rows[x_val][series_val] = row.get(detected_value_col, 0)

    # Fill missing series values with 0 and return in original x order.
    result = []
    for x_val in x_order:
        wide_row = wide_rows[x_val]
        for sk in series_keys:
            wide_row.setdefault(sk, 0)
        result.append(wide_row)

    return result
