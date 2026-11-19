from datetime import UTC, datetime, timedelta

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.routers.deps.time_range import (
    DEFAULT_USAGE_DAYS,
    MAX_USAGE_WINDOW_DAYS,
    TimeRangeBoundsQuery,
    resolve_usage_time_range,
    validate_time_range_window,
)


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


def test_resolve_usage_time_range_defaults_to_30_day_rolling_window():
    before = datetime.now(UTC)
    window = resolve_usage_time_range(start_time=None, end_time=None, days=None)
    after = datetime.now(UTC)
    span_days = (window.end_time - window.start_time).days
    assert span_days == DEFAULT_USAGE_DAYS
    assert window.end_time >= before
    assert window.end_time <= after + timedelta(seconds=1)


def test_resolve_usage_time_range_legacy_days_parameter():
    window = resolve_usage_time_range(start_time=None, end_time=None, days=7)
    assert (window.end_time - window.start_time).days == 7


def test_resolve_usage_time_range_rejects_partial_explicit_bounds():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="together"):
        resolve_usage_time_range(start_time=start, end_time=None, days=None)


def test_resolve_usage_time_range_rejects_span_over_max_days():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=MAX_USAGE_WINDOW_DAYS + 1)
    with pytest.raises(ValidationError, match="must not exceed"):
        resolve_usage_time_range(start_time=start, end_time=end, days=None)


def test_time_range_bounds_query_pydantic_rejects_inverted_range():
    start = datetime(2026, 1, 15, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="start_time must be before end_time"):
        TimeRangeBoundsQuery(start_time=start, end_time=end)