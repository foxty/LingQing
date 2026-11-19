"""FastAPI query deps for start_time / end_time (pairs with portal TimeRangePicker)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Self

from fastapi import Query
from pydantic import BaseModel, ConfigDict, model_validator

from apps.shared.core.exceptions import ValidationError

DEFAULT_USAGE_DAYS = 30
MAX_USAGE_WINDOW_DAYS = 90


@dataclass(frozen=True)
class TimeRangeWindow:
    start_time: datetime
    end_time: datetime


class TimeRangeBoundsQuery(BaseModel):
    """Cross-field rules for ISO datetime query bounds (Pydantic v2)."""

    model_config = ConfigDict(extra="forbid")

    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.start_time >= self.end_time:
            raise ValidationError("start_time must be before end_time")
        return self


def validate_time_range_window(start_time: datetime, end_time: datetime) -> TimeRangeWindow:
    parsed = TimeRangeBoundsQuery(start_time=start_time, end_time=end_time)
    return TimeRangeWindow(start_time=parsed.start_time, end_time=parsed.end_time)


def _enforce_max_span(start_time: datetime, end_time: datetime) -> None:
    span = end_time - start_time
    if span > timedelta(days=MAX_USAGE_WINDOW_DAYS):
        raise ValidationError(
            f"time window must not exceed {MAX_USAGE_WINDOW_DAYS} days",
            {"max_days": MAX_USAGE_WINDOW_DAYS},
        )


def resolve_usage_time_range(
    *,
    start_time: datetime | None,
    end_time: datetime | None,
    days: int | None,
) -> TimeRangeWindow:
    """Explicit bounds take precedence; otherwise rolling window from ``days`` (default 30)."""
    has_start = start_time is not None
    has_end = end_time is not None
    if has_start or has_end:
        if not (has_start and has_end):
            raise ValidationError(
                "start_time and end_time must be provided together",
                {"start_time": start_time, "end_time": end_time},
            )
        window = validate_time_range_window(start_time, end_time)
        _enforce_max_span(window.start_time, window.end_time)
        return window

    effective_days = days if days is not None else DEFAULT_USAGE_DAYS
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=effective_days)
    return validate_time_range_window(period_start, period_end)


def time_range_window(
    start_time: datetime | None = Query(None, description="Range start (UTC)"),
    end_time: datetime | None = Query(None, description="Range end (UTC)"),
    days: int | None = Query(
        None,
        ge=1,
        le=MAX_USAGE_WINDOW_DAYS,
        description="Rolling window when start_time/end_time omitted (default 30, max 90)",
    ),
) -> TimeRangeWindow:
    return resolve_usage_time_range(start_time=start_time, end_time=end_time, days=days)