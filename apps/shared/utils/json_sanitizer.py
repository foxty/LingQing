"""Utilities for producing JSON-safe data."""

import math
import numbers
from typing import Any


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        try:
            if not math.isfinite(float(value)):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    return value


def sanitize_json_data(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [sanitize_json_value(item) for item in data]
