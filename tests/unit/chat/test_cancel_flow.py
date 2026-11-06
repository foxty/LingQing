"""Tests for chat cancel run orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.tenant_app_service.chat.application.runs.cancel_flow import execute_cancel_agent_run


@pytest.mark.asyncio
async def test_execute_cancel_agent_run_delegates_after_auth():
    db = AsyncMock()
    cancelled = MagicMock(id="run-1")
    thread = MagicMock(user_id=10)

    with (
        patch(
            "apps.tenant_app_service.chat.application.threads.thread_service.ThreadService",
        ) as thread_svc_cls,
        patch(
            "apps.tenant_app_service.chat.application.runs.cancel_flow.ThreadRunService",
        ) as runs_cls,
    ):
        thread_svc_cls.return_value.get_thread = AsyncMock(return_value=thread)
        runs_cls.return_value.cancel_agent_run = AsyncMock(return_value=cancelled)
        result = await execute_cancel_agent_run(
            db,
            1,
            thread_id="thread-1",
            run_id="run-1",
            user_id=10,
        )

    assert result is cancelled
    runs_cls.return_value.cancel_agent_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_cancel_agent_run_rejects_wrong_user():
    db = AsyncMock()
    thread = MagicMock(user_id=99)

    with patch(
        "apps.tenant_app_service.chat.application.threads.thread_service.ThreadService",
    ) as thread_svc_cls:
        thread_svc_cls.return_value.get_thread = AsyncMock(return_value=thread)
        with pytest.raises(AuthorizationError):
            await execute_cancel_agent_run(
                db,
                1,
                thread_id="thread-1",
                run_id="run-1",
                user_id=10,
            )


@pytest.mark.asyncio
async def test_execute_cancel_agent_run_raises_when_thread_missing():
    db = AsyncMock()

    with patch(
        "apps.tenant_app_service.chat.application.threads.thread_service.ThreadService",
    ) as thread_svc_cls:
        thread_svc_cls.return_value.get_thread = AsyncMock(return_value=None)
        with pytest.raises(ResourceNotFoundError):
            await execute_cancel_agent_run(
                db,
                1,
                thread_id="thread-missing",
                run_id="run-1",
                user_id=10,
            )
