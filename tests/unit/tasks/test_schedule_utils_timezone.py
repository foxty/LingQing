from datetime import datetime, timezone

import pytest

from apps.shared.tasks.domain import SCHEDULE_TYPE_CRON
from apps.shared.tasks.scheduling.schedule_utils import compute_next_run_at, normalize_schedule_spec


def test_normalize_cron_schedule_with_timezone():
    normalized = normalize_schedule_spec(
        schedule_type=SCHEDULE_TYPE_CRON,
        schedule_spec="30 10 * * *",
        timezone_name="Asia/Shanghai",
    )

    assert normalized["cron"] == "30 10 * * *"
    assert normalized["timezone"] == "Asia/Shanghai"


def test_compute_next_run_at_uses_runtime_timezone_fallback():
    reference = datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc)

    next_run = compute_next_run_at(
        schedule_type=SCHEDULE_TYPE_CRON,
        schedule_spec={"cron": "30 10 * * *"},
        runtime_timezone="Asia/Shanghai",
        now=reference,
    )

    assert next_run is not None
    assert next_run == datetime(2026, 3, 31, 2, 30, tzinfo=timezone.utc)


def test_compute_next_run_at_handles_dst_timezone():
    # America/New_York switched to DST in March 2026 (UTC-4),
    # so 10:30 local should map to 14:30 UTC.
    reference = datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc)
    next_run = compute_next_run_at(
        schedule_type=SCHEDULE_TYPE_CRON,
        schedule_spec={"cron": "30 10 * * *", "timezone": "America/New_York"},
        now=reference,
    )

    assert next_run is not None
    assert next_run == datetime(2026, 3, 31, 14, 30, tzinfo=timezone.utc)


def test_normalize_cron_schedule_rejects_invalid_timezone():
    with pytest.raises(ValueError, match="valid IANA timezone"):
        normalize_schedule_spec(
            schedule_type=SCHEDULE_TYPE_CRON,
            schedule_spec="30 10 * * *",
            timezone_name="Mars/Olympus",
        )
