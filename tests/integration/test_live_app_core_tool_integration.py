"""Integration tests for live app core agent tools."""

import json
from pathlib import Path

import pytest

from apps.shared.db.models import AclGrant
from apps.tenant_app_service.agents.tools import live_app
from tests.integration.tool_integration_helpers import (
    SessionContext,
    build_runnable_config_for_actor,
    seed_actor_records,
    seed_base_records,
    seed_managed_data_source,
)


@pytest.mark.asyncio
async def test_live_app_tools_flow(async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(live_app, "app_db_session", lambda: SessionContext(async_db_session))
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / "live_apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(
            tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / "live_apps" / f"app_{app_id}"
        ),
    )

    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    created = await live_app.create_live_app.ainvoke(
        {"name": "integration-live-app", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    listed = await live_app.list_live_apps.ainvoke({}, config=runnable_config)
    listed_payload = json.loads(listed.content)
    assert any(item["app_id"] == app_id for item in listed_payload["apps"])

    loaded = await live_app.get_live_app.ainvoke({"app_id": app_id}, config=runnable_config)
    loaded_payload = json.loads(loaded.content)
    assert loaded_payload["app_id"] == app_id

    await live_app.write_app_file.ainvoke(
        {
            "app_id": app_id,
            "path": "src/integration.js",
            "content": "console.log('integration');",
        },
        config=runnable_config,
    )
    read_result = await live_app.read_app_file.ainvoke(
        {"app_id": app_id, "path": "src/integration.js"},
        config=runnable_config,
    )
    read_payload = json.loads(read_result.content)
    assert "integration" in read_payload["content"]


@pytest.mark.asyncio
async def test_live_app_list_respects_sharing(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(live_app, "app_db_session", lambda: SessionContext(async_db_session))
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / "live_apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(
            tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / "live_apps" / f"app_{app_id}"
        ),
    )

    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    other_user_id = 458
    other_thread_id = "thread_test_458_other"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=other_user_id,
        username="live_app_reader",
        role="analyst",
        thread_id=other_thread_id,
    )
    other_user_config = build_runnable_config_for_actor(
        runtime_context,
        user_id=other_user_id,
        username="live_app_reader",
        role="analyst",
        thread_id=other_thread_id,
    )

    created = await live_app.create_live_app.ainvoke(
        {"name": "shared-live-app", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]
    _artifact_id = created_payload["artifact"]["id"]

    before_share = await live_app.list_live_apps.ainvoke({}, config=other_user_config)
    before_share_payload = json.loads(before_share.content)
    assert all(item["app_id"] != app_id for item in before_share_payload["apps"])

    async_db_session.add(
        AclGrant(
            tenant_id=runtime_context.user.tenant_id,
            resource_type="app",
            resource_id=app_id,
            principal_type="user",
            principal_id=str(other_user_id),
            permission="read",
            effect="allow",
            created_by=runtime_context.user.user_id,
        )
    )
    await async_db_session.commit()

    after_share = await live_app.list_live_apps.ainvoke({}, config=other_user_config)
    after_share_payload = json.loads(after_share.content)
    assert any(item["app_id"] == app_id for item in after_share_payload["apps"])
