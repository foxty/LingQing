"""FastAPI query deps for start_time / end_time (pairs with portal TimeRangePicker)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Self

from fastapi import Query
from pydantic import BaseModel, ConfigDict, model_validator

from apps.shared.core.exceptions import ValidationError


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


def time_range_window(
    start_time: datetime = Query(..., description="Range start (UTC)"),
    end_time: datetime = Query(..., description="Range end (UTC)"),
) -> TimeRangeWindow:
    """Required bounds at the HTTP edge; ordering checked via Pydantic."""
    return validate_time_range_window(start_time, end_time)