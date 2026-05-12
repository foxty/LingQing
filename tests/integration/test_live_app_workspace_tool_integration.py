"""Integration tests for live app workspace and deployment agent tools."""

import json
from pathlib import Path

import pytest

from apps.shared.db.models import AclGrant
from apps.tenant_app_service.agents.tools import live_app
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus
from tests.integration.tool_integration_helpers import (
    SessionContext,
    build_runnable_config_for_actor,
    seed_actor_records,
    seed_base_records,
    seed_managed_data_source,
)


def _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path: Path) -> None:
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


@pytest.mark.asyncio
async def test_live_app_workspace_tools_flow(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    created = await live_app.create_live_app.ainvoke(
        {"name": "workspace-tool-integration", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Load SDK spec via read_skill_file
    from apps.tenant_app_service.agents.tools.skill_reference import read_skill_file

    spec = await read_skill_file.ainvoke(
        {
            "skill_name": "app-builder",
            "relative_path": "references/javascript_sdk_reference.md",
        },
        config=runnable_config,
    )
    assert spec.status == ToolResultStatus.SUCCESS
    spec_content = spec.content if isinstance(spec.content, str) else spec.content.get("content", "")
    assert "declare" in spec_content

    file_list = await live_app.list_app_files.ainvoke({"app_id": app_id}, config=runnable_config)
    file_list_payload = json.loads(file_list.content)
    assert "files" in file_list_payload

    migration_name = "integration_users_idx"
    migration_create = await live_app.create_db_migration.ainvoke(
        {
            "app_id": app_id,
            "migration_name": migration_name,
            "up_sql": "CREATE TABLE IF NOT EXISTS integration_users (id SERIAL PRIMARY KEY, name TEXT);",
            "down_sql": "DROP TABLE IF EXISTS integration_users;",
        },
        config=runnable_config,
    )
    assert migration_create.status == ToolResultStatus.SUCCESS

    migrations = await live_app.list_db_migrations.ainvoke({"app_id": app_id}, config=runnable_config)
    migrations_payload = json.loads(migrations.content)
    assert any(migration_name in item["name"] for item in migrations_payload.get("migrations", []))

    apply_result = await live_app.apply_db_migration.ainvoke(
        {"app_id": app_id, "migration_name": migration_name},
        config=runnable_config,
    )
    assert apply_result.status == ToolResultStatus.SUCCESS

    rollback_result = await live_app.rollback_db_migration.ainvoke(
        {"app_id": app_id, "migration_name": migration_name},
        config=runnable_config,
    )
    assert rollback_result.status == ToolResultStatus.SUCCESS

    remove_result = await live_app.remove_db_migration.ainvoke(
        {"app_id": app_id, "migration_name": migration_name},
        config=runnable_config,
    )
    assert remove_result.status == ToolResultStatus.SUCCESS

    await live_app.write_app_file.ainvoke(
        {
            "app_id": app_id,
            "path": "app.status.md",
            "content": "# status\n- integration test status file",
        },
        config=runnable_config,
    )

    commit_result = await live_app.commit_app_changes.ainvoke(
        {"app_id": app_id, "message": "integration commit"},
        config=runnable_config,
    )
    assert commit_result.status == ToolResultStatus.SUCCESS

    commits_result = await live_app.list_app_commits.ainvoke(
        {"app_id": app_id, "limit": 5},
        config=runnable_config,
    )
    commits_payload = json.loads(commits_result.content)
    commits = commits_payload.get("commits", [])
    assert len(commits) >= 1

    validation_result = await live_app.validate_live_app.ainvoke({"app_id": app_id}, config=runnable_config)
    assert validation_result.status == ToolResultStatus.SUCCESS

    deployment_state_result = await live_app.get_app_deployment_state.ainvoke(
        {"app_id": app_id},
        config=runnable_config,
    )
    deployment_state_payload = json.loads(deployment_state_result.content)
    assert "deployment_state" in deployment_state_payload

    promotions_result = await live_app.list_app_promotions.ainvoke(
        {"app_id": app_id, "limit": 5},
        config=runnable_config,
    )
    promotions_payload = json.loads(promotions_result.content)
    assert "promotions" in promotions_payload

    latest_commit = commits[0].get("sha") if commits else None
    promote_result = await live_app.promote_app_environment.ainvoke(
        {
            "app_id": app_id,
            "from_environment": "dev",
            "to_environment": "test",
            "source_commit": latest_commit or "",
            "dry_run": True,
        },
        config=runnable_config,
    )
    assert promote_result.status == ToolResultStatus.SUCCESS

    diff_result = await live_app.diff_app_environments.ainvoke(
        {"app_id": app_id, "from_environment": "dev", "to_environment": "test"},
        config=runnable_config,
    )
    diff_payload = json.loads(diff_result.content)
    assert "files" in diff_payload


@pytest.mark.asyncio
async def test_live_app_workspace_write_tools_require_write_access(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
    tmp_path: Path,
):
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)
    created = await live_app.create_live_app.ainvoke(
        {"name": "permission-check-live-app", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]
    _artifact_id = created_payload["artifact"]["id"]

    other_user_id = 460
    other_thread_id = "thread_test_460_other"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=other_user_id,
        username="live_app_shared_reader",
        role="analyst",
        thread_id=other_thread_id,
    )
    other_user_config = build_runnable_config_for_actor(
        runtime_context,
        user_id=other_user_id,
        username="live_app_shared_reader",
        role="analyst",
        thread_id=other_thread_id,
    )

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

    read_file_shared = await live_app.list_app_files.ainvoke({"app_id": app_id}, config=other_user_config)
    assert read_file_shared.status == ToolResultStatus.SUCCESS

    write_denied = await live_app.create_db_migration.ainvoke(
        {
            "app_id": app_id,
            "migration_name": "reader_should_not_write",
            "up_sql": "SELECT 1;",
        },
        config=other_user_config,
    )
    assert write_denied.status == ToolResultStatus.ERROR
