"""Reconcile orchestration before a new chat turn."""

from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.application.turn.reconcile_before_turn_flow import (
    execute_reconcile_before_new_turn,
)


@pytest.mark.asyncio
async def test_execute_reconcile_delegates_to_thread_run_service():
    db = AsyncMock()

    with patch(
        "apps.tenant_app_service.chat.application.turn.reconcile_before_turn_flow.ThreadRunService",
    ) as runs_cls:
        runs_cls.return_value.reconcile_before_new_turn = AsyncMock()

        await execute_reconcile_before_new_turn(
            db,
            1,
            thread_id="thread-1",
            agent_id=-1,
        )

    runs_cls.return_value.reconcile_before_new_turn.assert_awaited_once_with("thread-1", -1)
