"""Schedule parsing and next-run calculation utilities."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from apps.shared.tasks.domain import (
    SCHEDULE_TYPE_CRON,
    SCHEDULE_TYPE_ONCE,
    CronScheduleSpec,
    OnceScheduleSpec,
    ScheduleSpec,
)


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("run_at must include timezone information")
    return parsed.astimezone(UTC)


def _parse_relative_datetime(value: str, reference: datetime) -> datetime:
    matched = re.fullmatch(r"\+(\d+)([smhdw])", value)
    if not matched:
        raise ValueError(
            "Invalid once schedule_spec. Use ISO datetime with timezone "
            "or relative offset like +5m, +2h, +1d"
        )

    amount = int(matched.group(1))
    unit = matched.group(2)
    if amount <= 0:
        raise ValueError("Relative offset must be greater than 0")

    if unit == "s":
        delta = timedelta(seconds=amount)
    elif unit == "m":
        delta = timedelta(minutes=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    else:
        delta = timedelta(weeks=amount)
    return reference + delta


def _normalize_timezone(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("timezone cannot be empty")
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return candidate


def normalize_schedule_spec(
    schedule_type: str,
    schedule_spec: str,
    timezone_name: str | None = None,
) -> ScheduleSpec:
    """Validate and normalize schedule payload."""
    if schedule_type == SCHEDULE_TYPE_ONCE:
        schedule_spec = schedule_spec.strip()
        reference = datetime.now(UTC)
        if schedule_spec.startswith("+"):
            run_at = _parse_relative_datetime(schedule_spec, reference)
        else:
            run_at = _parse_iso_datetime(schedule_spec)
        return OnceScheduleSpec(run_at=run_at.isoformat())

    if schedule_type == SCHEDULE_TYPE_CRON:
        # Validate cron expression format and values.
        effective_timezone = _normalize_timezone(timezone_name) if timezone_name else "UTC"
        CronTrigger.from_crontab(schedule_spec, timezone=ZoneInfo(effective_timezone))
        normalized = CronScheduleSpec(cron=schedule_spec)
        normalized["timezone"] = effective_timezone
        return normalized

    raise ValueError(f"Unsupported schedule_type: {schedule_type}")


def compute_next_run_at(
    *,
    schedule_type: str,
    schedule_spec: ScheduleSpec | dict[str, Any],
    runtime_timezone: str | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """Compute next run time in UTC."""
    reference = now.astimezone(UTC) if now else datetime.now(UTC)

    if schedule_type == SCHEDULE_TYPE_ONCE:
        run_at_raw = schedule_spec.get("run_at")
        if not isinstance(run_at_raw, str):
            raise ValueError("schedule_spec.run_at is required for once schedule")
        run_at = _parse_iso_datetime(run_at_raw)
        return run_at if run_at > reference else None

    if schedule_type == SCHEDULE_TYPE_CRON:
        cron_expr = schedule_spec.get("cron")
        if not isinstance(cron_expr, str):
            raise ValueError("schedule_spec.cron is required for cron schedule")
        schedule_timezone_raw = schedule_spec.get("timezone")
        effective_timezone_name = (
            schedule_timezone_raw
            if isinstance(schedule_timezone_raw, str) and schedule_timezone_raw.strip()
            else runtime_timezone or "UTC"
        )
        normalized_timezone = _normalize_timezone(effective_timezone_name)
        trigger = CronTrigger.from_crontab(cron_expr, timezone=ZoneInfo(normalized_timezone))
        return trigger.get_next_fire_time(previous_fire_time=None, now=reference)

    raise ValueError(f"Unsupported schedule_type: {schedule_type}")
