"""Unit tests for turn admission (advisory lock + busy gate)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import ThreadBusyError
from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
from apps.tenant_app_service.chat.turn_admission import (
    assert_thread_accepts_new_user_turn,
    guard_thread_turn_start,
    thread_advisory_lock_keys,
    try_acquire_thread_turn_xact_lock,
)


def test_thread_advisory_lock_keys_stable():
    a = thread_advisory_lock_keys(1, "thread-abc")
    b = thread_advisory_lock_keys(1, "thread-abc")
    assert a == b
    assert thread_advisory_lock_keys(1, "other") != a


@pytest.mark.asyncio
async def test_try_acquire_thread_turn_xact_lock_raises_when_not_acquired():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = False
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(ThreadBusyError) as exc_info:
        await try_acquire_thread_turn_xact_lock(db, tenant_id=1, thread_id="t1")

    assert exc_info.value.details.get("reason") == "advisory_lock_not_acquired"


@pytest.mark.asyncio
async def test_assert_thread_accepts_new_user_turn_raises_when_busy():
    db = AsyncMock()
    with patch(
        "apps.tenant_app_service.chat.turn_admission.ThreadRunService.get_active_run",
        AsyncMock(
            return_value=MagicMock(
                run_id="run-1",
                run_status=AgentRunStatus.RUNNING,
                session_id="sess-1",
            )
        ),
    ):
        with pytest.raises(ThreadBusyError) as exc_info:
            await assert_thread_accepts_new_user_turn(
                db,
                tenant_id=1,
                thread_id="t1",
                agent_id=-1,
            )

    assert exc_info.value.details.get("run_status") == AgentRunStatus.RUNNING


@pytest.mark.asyncio
async def test_guard_thread_turn_start_skips_busy_check_for_hitl():
    db = AsyncMock()
    with patch(
        "apps.tenant_app_service.chat.turn_admission.try_acquire_thread_turn_xact_lock",
        AsyncMock(),
    ) as lock_mock:
        with patch(
            "apps.tenant_app_service.chat.turn_admission.assert_thread_accepts_new_user_turn",
            AsyncMock(),
        ) as busy_mock:
            await guard_thread_turn_start(
                db,
                tenant_id=1,
                thread_id="t1",
                agent_id=-1,
                skip_busy_check=True,
            )

    lock_mock.assert_awaited_once()
    busy_mock.assert_not_awaited()
