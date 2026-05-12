"""Integration tests for scheduler agent tools."""

import json

import pytest
from sqlalchemy import select

from apps.shared.db.models import AclGrant, ScheduledTask
from apps.tenant_app_service.agents.tools import scheduler
from apps.tenant_app_service.agents.tools.tool_result import ToolResult, ToolResultStatus
from tests.integration.tool_integration_helpers import (
    SessionContext,
    build_runnable_config_for_actor,
    seed_actor_records,
    seed_base_records,
)


@pytest.mark.asyncio
async def test_scheduler_tools_flow(async_db_session, runtime_context, runnable_config, monkeypatch):
    monkeypatch.setattr(scheduler, "app_db_session", lambda: SessionContext(async_db_session))
    await seed_base_records(async_db_session, runtime_context)

    created = await scheduler.schedule_task.ainvoke(
        {
            "task_description": "integration scheduled task",
            "schedule_type": "once",
            "schedule_spec": "+10m",
        },
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    task_id = created_payload["task_id"]

    listed = await scheduler.list_scheduled_tasks.ainvoke({}, config=runnable_config)
    listed_payload = json.loads(listed.content)
    assert listed_payload["count"] >= 1
    assert any(row["id"] == task_id for row in listed_payload["tasks"])

    got = await scheduler.get_scheduled_task.ainvoke({"task_id": task_id}, config=runnable_config)
    got_payload = json.loads(got.content)
    assert got_payload["id"] == task_id
    assert got_payload["name"] == "integration scheduled task"

    await scheduler.update_scheduled_task.ainvoke(
        {"task_id": task_id, "task_description": "integration scheduled task updated"},
        config=runnable_config,
    )
    task_after_update = await async_db_session.get(ScheduledTask, task_id)
    assert task_after_update is not None
    assert task_after_update.name == "integration scheduled task updated"

    await scheduler.update_scheduled_task.ainvoke(
        {
            "task_id": task_id,
            "schedule_type": "cron",
            "schedule_spec": "0 9 * * *",
            "schedule_timezone": "Asia/Shanghai",
        },
        config=runnable_config,
    )
    task_after_schedule_update = await async_db_session.get(ScheduledTask, task_id)
    assert task_after_schedule_update is not None
    assert task_after_schedule_update.schedule_type == "cron"
    assert task_after_schedule_update.schedule_spec["timezone"] == "Asia/Shanghai"

    cancelled = await scheduler.cancel_scheduled_task.ainvoke({"task_id": task_id}, config=runnable_config)
    cancelled_payload = json.loads(cancelled.content)
    assert cancelled_payload["status"] == "cancelled"

    task = await async_db_session.get(ScheduledTask, task_id)
    assert task is not None
    assert task.status == "cancelled"


@pytest.mark.asyncio
async def test_schedule_task_permission_denied(async_db_session, runtime_context, runnable_config, monkeypatch):
    monkeypatch.setattr(scheduler, "app_db_session", lambda: SessionContext(async_db_session))
    await seed_base_records(async_db_session, runtime_context)

    async def _deny(*args, **kwargs):
        return ToolResult.error_result(
            "You do not have permission to create scheduled tasks",
            code="PERMISSION_DENIED",
        )

    monkeypatch.setattr(scheduler, "tool_rbac_denied", _deny)

    denied = await scheduler.schedule_task.ainvoke(
        {
            "task_description": "blocked scheduled task",
            "schedule_type": "once",
            "schedule_spec": "+10m",
        },
        config=runnable_config,
    )
    assert denied.status == ToolResultStatus.ERROR
    assert denied.error is not None
    assert denied.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_scheduler_tool_access_respects_share_permission(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(scheduler, "app_db_session", lambda: SessionContext(async_db_session))
    await seed_base_records(async_db_session, runtime_context)

    other_user_id = 457
    other_thread_id = "thread_test_457_other"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=other_user_id,
        username="scheduler_reader",
        role="analyst",
        thread_id=other_thread_id,
    )
    other_user_config = build_runnable_config_for_actor(
        runtime_context,
        user_id=other_user_id,
        username="scheduler_reader",
        role="analyst",
        thread_id=other_thread_id,
    )

    created = await scheduler.schedule_task.ainvoke(
        {
            "task_description": "owner task for sharing",
            "schedule_type": "once",
            "schedule_spec": "+10m",
        },
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    task_id = created_payload["task_id"]

    denied_no_share = await scheduler.cancel_scheduled_task.ainvoke(
        {"task_id": task_id},
        config=other_user_config,
    )
    assert denied_no_share.status == ToolResultStatus.ERROR

    async_db_session.add(
        AclGrant(
            tenant_id=runtime_context.user.tenant_id,
            resource_type="scheduled_task",
            resource_id=task_id,
            principal_type="user",
            principal_id=str(other_user_id),
            permission="read",
            effect="allow",
            created_by=runtime_context.user.user_id,
        )
    )
    await async_db_session.commit()

    denied_read_share = await scheduler.update_scheduled_task.ainvoke(
        {
            "task_id": task_id,
            "task_description": "should fail for read share",
        },
        config=other_user_config,
    )
    assert denied_read_share.status == ToolResultStatus.ERROR

    share = (
        await async_db_session.execute(
            select(AclGrant).where(
                AclGrant.tenant_id == runtime_context.user.tenant_id,
                AclGrant.resource_type == "scheduled_task",
                AclGrant.resource_id == task_id,
                AclGrant.principal_type == "user",
                AclGrant.principal_id == str(other_user_id),
                AclGrant.effect == "allow",
            )
        )
    ).scalar_one()
    share.permission = "write"
    await async_db_session.commit()

    denied_write_share = await scheduler.cancel_scheduled_task.ainvoke(
        {"task_id": task_id},
        config=other_user_config,
    )
    assert denied_write_share.status == ToolResultStatus.ERROR

    owner_cancel = await scheduler.cancel_scheduled_task.ainvoke(
        {"task_id": task_id},
        config=runnable_config,
    )
    assert owner_cancel.status == ToolResultStatus.SUCCESS
