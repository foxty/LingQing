"""Integration tests for report agent tools."""

import json

import pytest
from sqlalchemy import select

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.models import AclGrant
from apps.tenant_app_service.agents.tools import report
from apps.tenant_app_service.agents.tools.tool_result import ToolResult, ToolResultStatus
from tests.integration.tool_integration_helpers import (
    build_runnable_config_for_actor,
    patch_agent_tool_db_session,
    seed_actor_records,
    seed_base_records,
)


@pytest.mark.asyncio
async def test_report_tools_flow(async_db_session, runtime_context, runnable_config, monkeypatch):
    patch_agent_tool_db_session(monkeypatch, report, async_db_session)
    await seed_base_records(async_db_session, runtime_context)

    created = await report.create_report.ainvoke(
        {"title": "Integration Report", "content": "hello report"},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    report_id = created_payload["report_id"]
    assert created_payload["artifact"] is not None
    assert created_payload["report_url"] == f"/reports/{report_id}"

    loaded = await report.get_report.ainvoke({"report_id": report_id}, config=runnable_config)
    loaded_payload = json.loads(loaded.content)
    assert loaded_payload["report_id"] == report_id
    assert loaded_payload["content"] == "hello report"

    await report.update_report.ainvoke(
        {"report_id": report_id, "content": "updated report content"},
        config=runnable_config,
    )
    reloaded = await report.get_report.ainvoke({"report_id": report_id}, config=runnable_config)
    reloaded_payload = json.loads(reloaded.content)
    assert reloaded_payload["content"] == "updated report content"
    assert reloaded_payload["title"] == "Integration Report"


@pytest.mark.asyncio
async def test_create_report_permission_denied(async_db_session, runtime_context, runnable_config, monkeypatch):
    patch_agent_tool_db_session(monkeypatch, report, async_db_session)
    await seed_base_records(async_db_session, runtime_context)

    async def _deny(*args, **kwargs):
        return ToolResult.error_result("You do not have permission to create reports", code="PERMISSION_DENIED")

    monkeypatch.setattr(report, "tool_rbac_denied", _deny)

    denied = await report.create_report.ainvoke(
        {"title": "Denied Report", "content": "blocked"},
        config=runnable_config,
    )
    assert denied.status == ToolResultStatus.ERROR
    assert denied.error is not None
    assert denied.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_report_tool_access_respects_share_permission(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    patch_agent_tool_db_session(monkeypatch, report, async_db_session)
    await seed_base_records(async_db_session, runtime_context)

    other_user_id = 456
    other_thread_id = "thread_test_456_other"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=other_user_id,
        username="otheruser",
        role="analyst",
        thread_id=other_thread_id,
    )
    other_user_config = build_runnable_config_for_actor(
        runtime_context,
        user_id=other_user_id,
        username="otheruser",
        role="analyst",
        thread_id=other_thread_id,
    )

    created = await report.create_report.ainvoke(
        {"title": "Shared Report", "content": "owner content"},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    report_id = created_payload["report_id"]

    with pytest.raises(AuthorizationError):
        await report.get_report.ainvoke({"report_id": report_id}, config=other_user_config)

    async_db_session.add(
        AclGrant(
            tenant_id=runtime_context.user.tenant_id,
            resource_type="report",
            resource_id=report_id,
            principal_type="user",
            principal_id=str(other_user_id),
            permission="read",
            effect="allow",
            created_by=runtime_context.user.user_id,
        )
    )
    await async_db_session.commit()

    shared_read = await report.get_report.ainvoke({"report_id": report_id}, config=other_user_config)
    shared_read_payload = json.loads(shared_read.content)
    assert shared_read_payload["report_id"] == report_id

    with pytest.raises(AuthorizationError):
        await report.update_report.ainvoke(
            {"report_id": report_id, "content": "should fail for read share"},
            config=other_user_config,
        )

    share = (
        await async_db_session.execute(
            select(AclGrant).where(
                AclGrant.tenant_id == runtime_context.user.tenant_id,
                AclGrant.resource_type == "report",
                AclGrant.resource_id == report_id,
                AclGrant.principal_type == "user",
                AclGrant.principal_id == str(other_user_id),
                AclGrant.effect == "allow",
            )
        )
    ).scalar_one()
    share.permission = "write"
    await async_db_session.commit()

    with pytest.raises(AuthorizationError):
        await report.update_report.ainvoke(
            {"report_id": report_id, "content": "still denied for non-owner"},
            config=other_user_config,
        )
