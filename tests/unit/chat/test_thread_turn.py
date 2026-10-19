"""Unit tests for per-thread turn admission."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import ThreadBusyError
from apps.tenant_app_service.chat.domain import SESSION_STATUS_RUNNING
from apps.tenant_app_service.chat.thread_turn import (
    assert_thread_accepts_new_user_turn,
    guard_thread_turn_start,
    thread_advisory_lock_keys,
    try_acquire_thread_turn_xact_lock,
)


def test_thread_advisory_lock_keys_stable():
    assert thread_advisory_lock_keys(2, "thread-abc") == thread_advisory_lock_keys(2, "thread-abc")
    assert thread_advisory_lock_keys(2, "thread-abc") != thread_advisory_lock_keys(2, "thread-xyz")


@pytest.mark.asyncio
async def test_try_acquire_thread_turn_xact_lock_raises_when_not_acquired():
    db = AsyncMock()
    lock_result = MagicMock()
    lock_result.scalar_one.return_value = False
    db.execute = AsyncMock(return_value=lock_result)

    with pytest.raises(ThreadBusyError) as exc_info:
        await try_acquire_thread_turn_xact_lock(db, tenant_id=1, thread_id="t1")

    assert exc_info.value.details.get("code") == "THREAD_BUSY"


@pytest.mark.asyncio
async def test_assert_thread_accepts_new_user_turn_raises_when_running():
    db = AsyncMock()
    with patch(
        "apps.tenant_app_service.chat.thread_turn.resolve_session_status",
        AsyncMock(
            return_value=type(
                "Status",
                (),
                {"status": SESSION_STATUS_RUNNING, "session_id": "sess-1"},
            )()
        ),
    ):
        with pytest.raises(ThreadBusyError) as exc_info:
            await assert_thread_accepts_new_user_turn(
                db,
                tenant_id=1,
                thread_id="t1",
                agent_id=-1,
            )
    assert exc_info.value.details.get("thread_status") == SESSION_STATUS_RUNNING


@pytest.mark.asyncio
async def test_guard_thread_turn_start_skips_busy_check_for_hitl():
    db = AsyncMock()
    with patch(
        "apps.tenant_app_service.chat.thread_turn.try_acquire_thread_turn_xact_lock",
        AsyncMock(),
    ) as lock_mock:
        with patch(
            "apps.tenant_app_service.chat.thread_turn.assert_thread_accepts_new_user_turn",
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
