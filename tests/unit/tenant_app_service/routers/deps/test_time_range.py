from datetime import UTC, datetime

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.routers.deps.time_range import TimeRangeBoundsQuery, validate_time_range_window


def test_validate_time_range_window_rejects_inverted_range():
    start = datetime(2026, 1, 15, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="start_time must be before end_time"):
        validate_time_range_window(start, end)


def test_validate_time_range_window_accepts_explicit_bounds():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 15, tzinfo=UTC)
    window = validate_time_range_window(start, end)
    assert window.start_time == start
    assert window.end_time == end


def test_time_range_bounds_query_pydantic_rejects_inverted_range():
    start = datetime(2026, 1, 15, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="start_time must be before end_time"):
        TimeRangeBoundsQuery(start_time=start, end_time=end)