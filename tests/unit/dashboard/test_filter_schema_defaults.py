"""Tests for dashboard filter schema defaults and normalization."""

from apps.shared.dashboard.schemas import DashboardFilterDTO, DashboardFilterUpdateDTO


def test_time_range_defaults_to_last_7_days_when_value_missing():
    dto = DashboardFilterDTO(
        id="filter-time",
        name="Time",
        type="time_range",
        paramKey="time",
        value=None,
    )

    assert dto.value == {"mode": "relative", "preset": "last_7_days"}


def test_time_range_legacy_now_range_falls_back_to_last_7_days():
    dto = DashboardFilterDTO(
        id="filter-time",
        name="Time",
        type="time_range",
        paramKey="time",
        value={"start": "now-30d", "end": "now"},
    )

    assert dto.value == {"mode": "relative", "preset": "last_7_days"}


def test_time_range_iso_start_end_becomes_custom_mode():
    dto = DashboardFilterDTO(
        id="filter-time",
        name="Time",
        type="time_range",
        paramKey="time",
        value={"start": "2026-03-01T00:00:00", "end": "2026-03-08T00:00:00"},
    )

    assert dto.value == {
        "mode": "absolute",
        "start": "2026-03-01T00:00:00",
        "end": "2026-03-08T00:00:00",
    }


def test_update_dto_time_range_legacy_now_range_falls_back_to_last_7_days():
    dto = DashboardFilterUpdateDTO(
        type="time_range",
        value={"start": "now-30d", "end": "now"},
    )

    assert dto.value == {"mode": "relative", "preset": "last_7_days"}
