import json
from types import SimpleNamespace

import pytest

from apps.tenant_app_service.agents.tools.scheduler import schedule_task
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_schedule_task_uses_runtime_timezone_fallback(monkeypatch, runnable_config):
    captured: dict = {}

    async def _fake_create_task_with_artifact(self, **kwargs):
        captured["create_task_kwargs"] = kwargs
        return SimpleNamespace(
            task=SimpleNamespace(
                id=1,
                name=kwargs["name"],
                task_type=kwargs["task_type"],
                schedule_type=kwargs["schedule_type"],
                schedule_spec=kwargs["schedule_spec"],
                next_run_at=kwargs["next_run_at"],
                status="pending",
            ),
            artifact=SimpleNamespace(model_dump=lambda: {"kind": "scheduled_task"}),
        )

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.scheduler.app_db_session",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.scheduler.ScheduledTaskService.create_task_with_artifact",
        _fake_create_task_with_artifact,
    )

    runtime = runnable_config["configurable"]["runtime"]
    runtime["user"]["timezone_iana"] = "Asia/Shanghai"

    result = await schedule_task.ainvoke(
        {
            "task_description": "daily sync",
            "schedule_type": "cron",
            "schedule_spec": "30 10 * * *",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert captured["create_task_kwargs"]["schedule_spec"]["timezone"] == "Asia/Shanghai"
    assert payload["schedule_timezone"] == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_schedule_task_prefers_explicit_schedule_timezone(monkeypatch, runnable_config):
    captured: dict = {}

    async def _fake_create_task_with_artifact(self, **kwargs):
        captured["create_task_kwargs"] = kwargs
        return SimpleNamespace(
            task=SimpleNamespace(
                id=2,
                name=kwargs["name"],
                task_type=kwargs["task_type"],
                schedule_type=kwargs["schedule_type"],
                schedule_spec=kwargs["schedule_spec"],
                next_run_at=kwargs["next_run_at"],
                status="pending",
            ),
            artifact=SimpleNamespace(model_dump=lambda: {"kind": "scheduled_task"}),
        )

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.scheduler.app_db_session",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.scheduler.ScheduledTaskService.create_task_with_artifact",
        _fake_create_task_with_artifact,
    )

    runtime = runnable_config["configurable"]["runtime"]
    runtime["user"]["timezone_iana"] = "Asia/Shanghai"

    result = await schedule_task.ainvoke(
        {
            "task_description": "daily sync",
            "schedule_type": "cron",
            "schedule_spec": "30 10 * * *",
            "schedule_timezone": "America/New_York",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert captured["create_task_kwargs"]["schedule_spec"]["timezone"] == "America/New_York"
    assert payload["schedule_timezone"] == "America/New_York"
