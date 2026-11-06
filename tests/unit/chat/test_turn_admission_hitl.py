"""Turn admission while a run is paused for HITL."""

from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.application.turn.admission import assert_thread_accepts_new_user_turn


@pytest.mark.asyncio
async def test_awaiting_hitl_does_not_block_new_user_turn():
    db = AsyncMock()

    with patch(
        "apps.tenant_app_service.chat.application.turn.admission.ThreadRunService",
    ) as svc_cls:
        svc_cls.return_value.any_active_runs = AsyncMock(return_value=False)
        await assert_thread_accepts_new_user_turn(
            db,
            tenant_id=1,
            thread_id="thread-1",
            agent_id=-1,
        )


@pytest.mark.asyncio
async def test_running_still_blocks_new_user_turn():
    from apps.shared.core.exceptions import ThreadBusyError
    from apps.tenant_app_service.chat.domain.agent_run.status import AgentRunStatus

    db = AsyncMock()
    blocking = AsyncMock(
        id="run-1",
        session_id="sess-1",
        status=AgentRunStatus.RUNNING,
    )

    with patch(
        "apps.tenant_app_service.chat.application.turn.admission.ThreadRunService",
    ) as svc_cls:
        svc_cls.return_value.any_active_runs = AsyncMock(return_value=True)
        svc_cls.return_value.get_active_runs = AsyncMock(return_value=[blocking])
        with pytest.raises(ThreadBusyError):
            await assert_thread_accepts_new_user_turn(
                db,
                tenant_id=1,
                thread_id="thread-1",
                agent_id=-1,
            )
