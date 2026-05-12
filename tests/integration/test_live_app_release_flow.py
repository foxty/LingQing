"""Integration test for live app dev->test->prod release flow."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.core.auth import get_current_user
from apps.shared.db.models import DataSource, Tenant, User
from apps.shared.db.session import get_db
from apps.shared.live_app.service import LiveAppService
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.server import app


def _postgres_config_from_session(async_db_session) -> dict:
    url = async_db_session.bind.engine.url
    return {
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
        "password": url.password,
    }


@pytest.mark.asyncio
async def test_live_app_end_to_end_release_flow(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(name="tenant_live_app_release_flow", slug="tenant_live_app_release_flow", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_release_flow_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_release_flow",
        type="postgres",
        managed=True,
        config=_postgres_config_from_session(async_db_session),
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    app_record = (
        await service.create_app_with_artifact(
            name="release_flow_app",
            description="basic layout and table app",
            owner_id=user.id,
            data_source_id=managed_ds.id,
        )
    ).app

    await service.write_file(
        app_record.app_id,
        "src/layout.js",
        "export const layout = '<main><h1>Sales Dashboard</h1></main>';",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.write_file(
        app_record.app_id,
        "src/table.js",
        "export const tableColumns = ['id', 'name', 'amount'];",
        environment="dev",
        actor_user_id=user.id,
    )

    commit_result = await service.commit_changes(
        app_record.app_id,
        environment="dev",
        commit_message="build basic layout and table",
        actor_user_id=user.id,
    )
    assert commit_result["committed"] is True

    validation = await service.validate_app(app_record.app_id, environment="dev")
    assert validation["valid"] is True
    assert all(c["status"] in ("pass", "skip") for c in validation["checks"])

    commits = await service.list_commits(app_record.app_id, environment="dev", limit=1)
    source_commit = commits["commits"][0]["sha"]

    test_promotion = await service.promote_environment(
        app_record.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=source_commit,
        actor_user_id=user.id,
    )
    assert test_promotion["deployment_state"]["test"] == source_commit

    prod_promotion = await service.promote_environment(
        app_record.app_id,
        from_environment="test",
        to_environment="prod",
        source_commit=source_commit,
        actor_user_id=user.id,
    )
    assert prod_promotion["deployment_state"]["prod"] == source_commit

    prod_layout = await service.read_file(app_record.app_id, "src/layout.js", environment="prod")
    prod_table = await service.read_file(app_record.app_id, "src/table.js", environment="prod")
    assert "Sales Dashboard" in prod_layout["content"]
    assert "tableColumns" in prod_table["content"]

    deployment_state = await service.get_deployment_state(app_record.app_id)
    assert deployment_state["deployment_state"]["test"] == source_commit
    assert deployment_state["deployment_state"]["prod"] == source_commit

    promotions = await service.list_promotions(app_record.app_id, limit=10)
    assert len(promotions["promotions"]) >= 2
    transitions = {(item["from_environment"], item["to_environment"]) for item in promotions["promotions"]}
    assert ("dev", "test") in transitions
    assert ("test", "prod") in transitions


@pytest.mark.asyncio
async def test_live_app_release_supports_rollback_and_forward_by_commit(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(name="tenant_live_app_release_rollback", slug="tenant_live_app_release_rollback", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_release_rollback_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_release_rollback",
        type="postgres",
        managed=True,
        config=_postgres_config_from_session(async_db_session),
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    app_record = (
        await service.create_app_with_artifact(
            name="release_flow_rollback_app",
            owner_id=user.id,
            data_source_id=managed_ds.id,
        )
    ).app

    await service.write_file(
        app_record.app_id,
        "src/layout.js",
        "export const version = 'v1';",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.commit_changes(
        app_record.app_id,
        environment="dev",
        commit_message="v1",
        actor_user_id=user.id,
    )

    await service.write_file(
        app_record.app_id,
        "src/layout.js",
        "export const version = 'v2';",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.commit_changes(
        app_record.app_id,
        environment="dev",
        commit_message="v2",
        actor_user_id=user.id,
    )

    commits = await service.list_commits(app_record.app_id, environment="dev", limit=10)
    latest_commit = commits["commits"][0]["sha"]
    older_commit = commits["commits"][1]["sha"]
    assert latest_commit != older_commit

    # Release latest commit first.
    await service.promote_environment(
        app_record.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=latest_commit,
        actor_user_id=user.id,
    )
    await service.promote_environment(
        app_record.app_id,
        from_environment="test",
        to_environment="prod",
        source_commit=latest_commit,
        actor_user_id=user.id,
    )
    prod_v2 = await service.read_file(app_record.app_id, "src/layout.js", environment="prod")
    assert "v2" in prod_v2["content"]

    # Roll back by promoting older dev commit.
    await service.promote_environment(
        app_record.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=older_commit,
        actor_user_id=user.id,
    )
    await service.promote_environment(
        app_record.app_id,
        from_environment="test",
        to_environment="prod",
        source_commit=older_commit,
        actor_user_id=user.id,
    )
    prod_v1 = await service.read_file(app_record.app_id, "src/layout.js", environment="prod")
    assert "v1" in prod_v1["content"]

    # Move forward again to latest commit.
    await service.promote_environment(
        app_record.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=latest_commit,
        actor_user_id=user.id,
    )
    await service.promote_environment(
        app_record.app_id,
        from_environment="test",
        to_environment="prod",
        source_commit=latest_commit,
        actor_user_id=user.id,
    )
    prod_v2_again = await service.read_file(app_record.app_id, "src/layout.js", environment="prod")
    assert "v2" in prod_v2_again["content"]


@pytest.mark.asyncio
async def test_live_app_entry_preview_is_environment_aware(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(name="tenant_live_app_entry_preview", slug="tenant_live_app_entry_preview", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_entry_preview_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_entry_preview",
        type="postgres",
        managed=True,
        config=_postgres_config_from_session(async_db_session),
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    app_record = (
        await service.create_app_with_artifact(
            name="entry_preview_app",
            owner_id=user.id,
            data_source_id=managed_ds.id,
        )
    ).app

    await service.write_file(
        app_record.app_id,
        "entry.html",
        "<html><body>entry v1</body></html>",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.commit_changes(
        app_record.app_id,
        environment="dev",
        commit_message="entry v1",
        actor_user_id=user.id,
    )
    commits_after_v1 = await service.list_commits(app_record.app_id, environment="dev", limit=1)
    commit_v1 = commits_after_v1["commits"][0]["sha"]

    await service.promote_environment(
        app_record.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=commit_v1,
        actor_user_id=user.id,
    )

    await service.write_file(
        app_record.app_id,
        "entry.html",
        "<html><body>entry v2</body></html>",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.commit_changes(
        app_record.app_id,
        environment="dev",
        commit_message="entry v2",
        actor_user_id=user.id,
    )

    dev_entry = await service.get_entry_page(app_record.app_id, environment="dev")
    test_entry = await service.get_entry_page(app_record.app_id, environment="test")
    prod_entry = await service.get_entry_page(app_record.app_id, environment="prod")

    assert "entry v2" in dev_entry["html"]
    assert dev_entry["deployed_commit"] is None

    assert "entry v1" in test_entry["html"]
    assert test_entry["deployed_commit"] == commit_v1

    assert "Live App ready." in prod_entry["html"]
    assert prod_entry["deployed_commit"] is None


@pytest.mark.asyncio
async def test_live_app_entry_api_preview_supports_env_and_invalid_env(async_db_session, monkeypatch, tmp_path: Path):
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

    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_local = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with test_session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    tenant_id: int
    user_id: int
    app_id: int
    commit_v1: str
    async with test_session_local() as seed_session:
        tenant = Tenant(name="tenant_live_app_entry_api", slug="tenant_live_app_entry_api", config=None)
        seed_session.add(tenant)
        await seed_session.flush()

        user = User(
            username="live_app_entry_api_user",
            email=None,
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
        )
        seed_session.add(user)
        await seed_session.flush()

        managed_ds = DataSource(
            tenant_id=tenant.id,
            name="managed_ds_entry_api",
            type="postgres",
            managed=True,
            config=_postgres_config_from_session(seed_session),
            owner_id=user.id,
        )
        seed_session.add(managed_ds)
        await seed_session.flush()

        service = LiveAppService.create(tenant_id=tenant.id, db_session=seed_session)
        app_record = (
            await service.create_app_with_artifact(
                name="entry_api_app",
                owner_id=user.id,
                data_source_id=managed_ds.id,
            )
        ).app
        await service.write_file(
            app_record.app_id,
            "entry.html",
            "<html><body>entry api v1</body></html>",
            environment="dev",
            actor_user_id=user.id,
        )
        await service.commit_changes(
            app_record.app_id,
            environment="dev",
            commit_message="entry api v1",
            actor_user_id=user.id,
        )
        commits = await service.list_commits(app_record.app_id, environment="dev", limit=1)
        commit_v1 = commits["commits"][0]["sha"]
        await service.promote_environment(
            app_record.app_id,
            from_environment="dev",
            to_environment="test",
            source_commit=commit_v1,
            actor_user_id=user.id,
        )
        await service.write_file(
            app_record.app_id,
            "entry.html",
            "<html><body>entry api v2</body></html>",
            environment="dev",
            actor_user_id=user.id,
        )
        await service.commit_changes(
            app_record.app_id,
            environment="dev",
            commit_message="entry api v2",
            actor_user_id=user.id,
        )
        await seed_session.commit()

        tenant_id = tenant.id
        user_id = user.id
        app_id = app_record.app_id

    async def _fake_user():
        return UserDTO(
            id=user_id, username="live_app_entry_api_user", role="admin", tenant_id=tenant_id, tenant_name="t"
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        client = TestClient(app)

        dev_response = client.get(f"/apps/{app_id}/dev/entry")
        assert dev_response.status_code == 200
        assert "text/html" in dev_response.headers.get("content-type", "")
        assert "entry api v2" in dev_response.text
        assert "lq-sdk.v" in dev_response.text

        test_response = client.get(f"/apps/{app_id}/test/entry")
        assert test_response.status_code == 200
        assert "text/html" in test_response.headers.get("content-type", "")
        assert "entry api v1" in test_response.text

        invalid_response = client.get(f"/apps/{app_id}/stage/entry")
        assert invalid_response.status_code == 400
        invalid_payload = invalid_response.json()
        assert invalid_payload["code"] == "APP_INVALID_ENVIRONMENT"
        assert invalid_payload["details"]["environment"] == "stage"
    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_validate_app_detects_empty_entry(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(name="tenant_validate_empty", slug="tenant-validate-empty", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="validate_empty_user", email=None, hashed_password="h", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    ds = DataSource(
        tenant_id=tenant.id,
        name="ds_validate_empty",
        type="postgres",
        managed=True,
        config=_postgres_config_from_session(async_db_session),
        owner_id=user.id,
    )
    async_db_session.add(ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    app_record = (
        await service.create_app_with_artifact(name="validate_empty_app", owner_id=user.id, data_source_id=ds.id)
    ).app

    await service.write_file(app_record.app_id, "entry.html", "   ", environment="dev", actor_user_id=user.id)

    result = await service.validate_app(app_record.app_id, environment="dev")
    assert result["valid"] is False
    entry_check = next(c for c in result["checks"] if c["check"] == "entry_file")
    assert entry_check["status"] == "fail"


@pytest.mark.asyncio
async def test_validate_app_detects_invalid_sql(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(name="tenant_validate_sql", slug="tenant-validate-sql", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="validate_sql_user", email=None, hashed_password="h", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    ds = DataSource(
        tenant_id=tenant.id,
        name="ds_validate_sql",
        type="postgres",
        managed=True,
        config=_postgres_config_from_session(async_db_session),
        owner_id=user.id,
    )
    async_db_session.add(ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    app_record = (
        await service.create_app_with_artifact(name="validate_sql_app", owner_id=user.id, data_source_id=ds.id)
    ).app

    html_with_bad_sql = (
        "<html><head></head><body>"
        '<lq-data-table source="SELECT * FROM nonexistent_table_xyz" table="t"></lq-data-table>'
        "</body></html>"
    )
    await service.write_file(
        app_record.app_id, "entry.html", html_with_bad_sql, environment="dev", actor_user_id=user.id
    )

    result = await service.validate_app(app_record.app_id, environment="dev")
    assert result["valid"] is False
    sql_check = next(c for c in result["checks"] if c["check"] == "sql_validation")
    assert sql_check["status"] == "fail"
    assert len(sql_check["errors"]) == 1


@pytest.mark.asyncio
async def test_validate_app_warns_on_unapplied_migration(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(name="tenant_validate_mig", slug="tenant-validate-mig", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="validate_mig_user", email=None, hashed_password="h", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    ds = DataSource(
        tenant_id=tenant.id,
        name="ds_validate_mig",
        type="postgres",
        managed=True,
        config=_postgres_config_from_session(async_db_session),
        owner_id=user.id,
    )
    async_db_session.add(ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    app_record = (
        await service.create_app_with_artifact(name="validate_mig_app", owner_id=user.id, data_source_id=ds.id)
    ).app

    await service.create_migration(
        app_record.app_id,
        migration_name="001_pending_table",
        up_sql="CREATE TABLE pending_test (id SERIAL PRIMARY KEY);",
        down_sql="DROP TABLE IF EXISTS pending_test;",
        environment="dev",
        actor_user_id=user.id,
    )

    result = await service.validate_app(app_record.app_id, environment="dev")
    assert result["valid"] is False
    mig_check = next(c for c in result["checks"] if c["check"] == "migrations")
    assert mig_check["status"] == "fail"
    assert "001_pending_table" in mig_check["unapplied"]
