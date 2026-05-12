"""Unit tests for scheduled agent_run task executor."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.shared.tasks.domain import ScheduledTaskDomain
from apps.tenant_app_service.chat.schemas import ChatResponse, Message
from apps.tenant_app_service.tasks.agent_run_executor import execute_agent_run_task


def _task(**task_config) -> ScheduledTaskDomain:
    now = datetime.now(timezone.utc)
    return ScheduledTaskDomain(
        id=1,
        tenant_id=1,
        user_id=2,
        name="agent task",
        task_type="agent_run",
        task_config=task_config,
        schedule_type="once",
        schedule_spec={},
        status="running",
        next_run_at=None,
        last_run_at=None,
        notification_channels=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_execute_agent_run_task_returns_context(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class FakeChatService:
        def __init__(self, tenant_id, db):
            self.tenant_id = tenant_id

        async def run_headless(self, **kwargs):
            assert kwargs["user_id"] == 2
            assert kwargs["agent_id"] == 10
            assert kwargs["message"] == "Summarize docs"
            assert kwargs["origin_thread_id"] == "thread_abc"
            assert kwargs["task_name"] == "agent task"
            assert "thread_mode" not in kwargs
            return ChatResponse(
                response=Message(
                    role="ai",
                    content="Summary complete.",
                    agent_id=10,
                    thread_id="thread_abc",
                    session_id="session_xyz",
                ),
                agent_id=10,
                tenant_id=1,
            )

    monkeypatch.setattr("apps.tenant_app_service.tasks.agent_run_executor.app_db_session", FakeSession)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.ChatService",
        FakeChatService,
    )
    deliver_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.deliver_scheduled_agent_run_to_slack",
        deliver_mock,
    )
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor._persist_origin_thread_id_if_missing",
        persist_mock,
    )

    result = await execute_agent_run_task(
        _task(
            agent_id=10,
            task_description="Summarize docs",
            origin_thread_id="thread_abc",
        )
    )

    assert result.success is True
    assert result.payload["status"] == "agent_execution_complete"
    assert result.payload["response_content"] == "Summary complete."
    ctx = result.payload["execution_context"]
    assert ctx["tenant_id"] == 1
    assert ctx["user_id"] == 2
    assert ctx["agent_id"] == 10
    assert ctx["thread_id"] == "thread_abc"
    assert ctx["origin_thread_id"] == "thread_abc"
    assert ctx["session_id"] == "session_xyz"
    assert result.payload["slack_thread_delivered"] is True
    persist_mock.assert_not_awaited()
    deliver_mock.assert_awaited_once()
    call_kwargs = deliver_mock.await_args.kwargs
    assert call_kwargs["origin_thread_id"] == "thread_abc"
    assert call_kwargs["response_text"] == "Summary complete."


@pytest.mark.asyncio
async def test_execute_agent_run_task_persists_origin_thread_when_missing(monkeypatch):
    created_thread_id = "1_2_-1_new-thread"

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class FakeChatService:
        def __init__(self, tenant_id, db):
            pass

        async def run_headless(self, **kwargs):
            assert kwargs["origin_thread_id"] is None
            return ChatResponse(
                response=Message(
                    role="ai",
                    content="Done.",
                    agent_id=-1,
                    thread_id=created_thread_id,
                    session_id="session_new",
                ),
                agent_id=-1,
                tenant_id=1,
            )

    monkeypatch.setattr("apps.tenant_app_service.tasks.agent_run_executor.app_db_session", FakeSession)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.ChatService",
        FakeChatService,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.deliver_scheduled_agent_run_to_slack",
        AsyncMock(return_value=False),
    )
    persist_mock = AsyncMock()
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor._persist_origin_thread_id_if_missing",
        persist_mock,
    )

    result = await execute_agent_run_task(
        _task(
            agent_id=-1,
            task_description="Tell a joke",
        )
    )

    assert result.success is True
    assert result.payload["execution_context"]["thread_id"] == created_thread_id
    assert result.payload["execution_context"]["origin_thread_id"] == created_thread_id
    persist_mock.assert_awaited_once()
    assert persist_mock.await_args.kwargs["origin_thread_id"] == created_thread_id


@pytest.mark.asyncio
async def test_execute_agent_run_task_missing_agent_id_raises():
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=2,
        task_config={"task_description": "Do something"},
    )

    with pytest.raises(ValueError, match="task_config.agent_id is required"):
        await execute_agent_run_task(task)


@pytest.mark.asyncio
async def test_execute_agent_run_task_missing_task_description_raises():
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=2,
        task_config={"agent_id": -1},
    )

    with pytest.raises(ValueError, match="task_config.task_description is required"):
        await execute_agent_run_task(task)


@pytest.mark.asyncio
async def test_execute_agent_run_task_returns_failure_result(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class FakeChatService:
        def __init__(self, tenant_id, db):
            pass

        async def run_headless(self, **_kwargs):
            raise RuntimeError("chat failed")

    monkeypatch.setattr("apps.tenant_app_service.tasks.agent_run_executor.app_db_session", FakeSession)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.ChatService",
        FakeChatService,
    )
    deliver_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.deliver_scheduled_agent_run_to_slack",
        deliver_mock,
    )

    result = await execute_agent_run_task(
        _task(
            agent_id=-1,
            task_description="Tell a joke",
            origin_thread_id="thread_origin",
        ),
    )

    assert result.success is False
    assert result.payload["status"] == "agent_execution_failed"
    assert result.error_message == "chat failed"
    assert result.payload["slack_thread_delivered"] is True
    deliver_mock.assert_awaited_once()
    assert deliver_mock.await_args.kwargs["origin_thread_id"] == "thread_origin"
    assert deliver_mock.await_args.kwargs["response_text"] == (
        "Sorry, I couldn't process that request. Please try again."
    )


@pytest.mark.asyncio
async def test_execute_agent_run_task_failure_skips_delivery_without_origin_thread(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class FakeChatService:
        def __init__(self, tenant_id, db):
            pass

        async def run_headless(self, **_kwargs):
            raise RuntimeError("chat failed")

    monkeypatch.setattr("apps.tenant_app_service.tasks.agent_run_executor.app_db_session", FakeSession)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.ChatService",
        FakeChatService,
    )
    deliver_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.deliver_scheduled_agent_run_to_slack",
        deliver_mock,
    )

    result = await execute_agent_run_task(
        _task(agent_id=-1, task_description="Tell a joke"),
    )

    assert result.success is False
    assert result.payload["slack_thread_delivered"] is False
    deliver_mock.assert_not_awaited()
