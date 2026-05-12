import pytest

from apps.shared.tasks.system.handler_result import (
    SystemTaskHandlerResult,
    system_task_failed,
    system_task_partial,
    system_task_success,
)
from apps.shared.tasks.system.jobs import asset_sync


def test_build_sync_error_message():
    assert (
        asset_sync._build_sync_error_message(total_errors=2, total_updated=0)
        == "Asset metadata sync failed with 2 error(s)"
    )
    assert (
        asset_sync._build_sync_error_message(total_errors=1, total_updated=1)
        == "Asset metadata sync completed with 1 error(s) and 1 update(s)"
    )


def test_system_task_handler_result_success():
    result = system_task_success(total_errors=0, total_updated=1)
    assert result.success is True
    assert result.error_message is None
    assert result.to_payload()["outcome"] == "success"
    assert result.to_payload()["total_updated"] == 1


def test_system_task_handler_result_partial_and_failed():
    partial = system_task_partial("partial failure", total_errors=1, total_updated=1)
    failed = system_task_failed("all failed", total_errors=2, total_updated=0)

    assert partial.success is False
    assert partial.outcome == "partial"
    assert partial.error_message == "partial failure"

    assert failed.success is False
    assert failed.outcome == "failed"
    assert failed.to_payload()["error_message"] == "all failed"


@pytest.mark.parametrize(
    ("factory", "expected_outcome"),
    [
        (lambda: system_task_success(), "success"),
        (lambda: system_task_partial("warn", total_errors=1), "partial"),
        (lambda: system_task_failed("boom", total_errors=2), "failed"),
    ],
)
def test_system_task_handler_result_outcomes(factory, expected_outcome):
    result = factory()
    assert isinstance(result, SystemTaskHandlerResult)
    assert result.outcome == expected_outcome
