"""Unit tests for live app service."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import DataSource, LiveApp, Tenant, User
from apps.shared.live_app.service import LiveAppService
from apps.shared.live_app.workspace import LiveAppWriteLockTimeoutError, get_latest_commit_for_app_environment


@pytest.mark.asyncio
async def test_service_factory_does_not_bootstrap_workspace(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_factory", slug="tenant_live_app_service_factory", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    def _fail_bootstrap(_tenant_id: int, _app_id: int):
        raise AssertionError("factory should not bootstrap workspace")

    monkeypatch.setattr("apps.shared.live_app.service.init_app_repo", _fail_bootstrap)
    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    assert service.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_create_app_bootstraps_repo_and_dev_entry(async_db_session, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / f"app_{app_id}"),
    )

    tenant = Tenant(name="tenant_live_app_service_create_app", slug="tenant_live_app_service_create_app", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_create_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_create_app",
        type="postgres",
        managed=True,
        config={},
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    ensured_schemas: list[str] = []

    async def _fake_ensure_schema(self, *, data_source_id: int, schema_name: str):
        assert data_source_id == managed_ds.id
        ensured_schemas.append(schema_name)

    monkeypatch.setattr("apps.shared.live_app.data_executor.LiveAppDataExecutor.ensure_schema", _fake_ensure_schema)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = (
        await service.create_app_with_artifact(name="create_app_case", description="test app", owner_id=user.id)
    ).app

    app_root = tmp_path / "tenants" / f"tenant_{tenant.id}" / "apps" / f"app_{result.app_id}"
    env_root = app_root / "env"
    dev_entry_path = env_root / "dev" / "entry.html"
    test_entry_path = env_root / "test" / "entry.html"
    prod_entry_path = env_root / "prod" / "entry.html"
    assert result.name == "create_app_case"
    assert result.data_source_id == managed_ds.id
    assert (app_root / ".git").exists()
    assert dev_entry_path.exists()
    assert test_entry_path.exists()
    assert prod_entry_path.exists()
    assert set(ensured_schemas) == {
        f"app_{result.app_id}_dev",
        f"app_{result.app_id}_test",
        f"app_{result.app_id}",
    }


@pytest.mark.asyncio
async def test_create_app_rejects_unmanaged_data_source(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(
        name="tenant_live_app_service_unmanaged_ds", slug="tenant_live_app_service_unmanaged_ds", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_unmanaged_ds_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    unmanaged_ds = DataSource(
        tenant_id=tenant.id,
        name="external_ds",
        type="postgres",
        managed=False,
        config={},
        owner_id=user.id,
    )
    async_db_session.add(unmanaged_ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ValidationError) as exc:
        (
            await service.create_app_with_artifact(
                name="create_app_unmanaged", owner_id=user.id, data_source_id=unmanaged_ds.id
            )
        ).app

    assert exc.value.details["code"] == "APP_DATASOURCE_NOT_MANAGED"


@pytest.mark.asyncio
async def test_create_app_requires_managed_data_source_when_not_specified(
    async_db_session, monkeypatch, tmp_path: Path
):
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

    tenant = Tenant(
        name="tenant_live_app_service_missing_managed_ds",
        slug="tenant_live_app_service_missing_managed_ds",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_missing_managed_ds_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ValidationError) as exc:
        (await service.create_app_with_artifact(name="create_app_without_ds", owner_id=user.id)).app

    assert exc.value.details["code"] == "APP_MANAGED_DATASOURCE_REQUIRED"


@pytest.mark.asyncio
async def test_create_app_schema_init_failure_raises_internal_error(async_db_session, monkeypatch, tmp_path: Path):
    from apps.shared.core.exceptions import InternalServiceError

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

    tenant = Tenant(name="tenant_live_app_service_schema_fail", slug="tenant_live_app_service_schema_fail", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_schema_fail_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_schema_fail",
        type="postgres",
        managed=True,
        config={},
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    async def _fake_ensure_schema(self, *, data_source_id: int, schema_name: str):
        raise RuntimeError("boom")

    monkeypatch.setattr("apps.shared.live_app.data_executor.LiveAppDataExecutor.ensure_schema", _fake_ensure_schema)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(InternalServiceError) as exc:
        (await service.create_app_with_artifact(name="create_app_schema_fail", owner_id=user.id)).app

    assert exc.value.details["code"] == "APP_SCHEMA_INIT_FAILED"


@pytest.mark.asyncio
async def test_get_app_returns_live_app_record(async_db_session):
    tenant = Tenant(name="tenant_live_app_service_get_app", slug="tenant_live_app_service_get_app", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_get_app_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(
        tenant_id=tenant.id,
        owner_id=user.id,
        name="service_app_get",
        app_config={"deployed_commits": {"dev": "d1", "test": "t1", "prod": None}},
    )
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = await service.get_app(live_app.id)

    assert result.app_id == live_app.id
    assert result.name == "service_app_get"
    assert result.deployment_state.dev == "d1"
    assert result.deployment_state.test == "t1"
    assert result.updated_at is not None


@pytest.mark.asyncio
async def test_list_apps_returns_tenant_scoped_records(async_db_session):
    tenant = Tenant(name="tenant_live_app_service_list_apps", slug="tenant_live_app_service_list_apps", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    other_tenant = Tenant(
        name="tenant_live_app_service_list_apps_other", slug="tenant_live_app_service_list_apps_other", config=None
    )
    async_db_session.add(other_tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_list_apps_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    other_user = User(
        username="live_app_service_list_apps_other_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=other_tenant.id,
    )
    async_db_session.add(other_user)
    await async_db_session.flush()

    app_one = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="tenant_app_one")
    app_two = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="tenant_app_two")
    foreign_app = LiveApp(tenant_id=other_tenant.id, owner_id=other_user.id, name="foreign_app")
    async_db_session.add_all([app_one, app_two, foreign_app])
    await async_db_session.commit()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = await service.list_apps(user.id, has_artifacts_manage=True)

    assert len(result) == 2
    returned_names = {item.name for item in result}
    assert returned_names == {"tenant_app_one", "tenant_app_two"}
    assert all(item.deployment_state is not None for item in result)


@pytest.mark.asyncio
async def test_get_entry_page_returns_live_app_content(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_get", slug="tenant_live_app_service_get", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(live_app.id, "entry.html", "<html>service</html>")
    result = await service.get_entry_page(live_app.id)

    assert result["app_id"] == live_app.id
    assert result["sdk_version"] == "1.0"
    assert result["deployed_commit"] is None
    assert result["html"] == "<html>service</html>"


@pytest.mark.asyncio
async def test_write_file_maps_lock_timeout_to_validation_error(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_lock", slug="tenant_live_app_service_lock", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_lock_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_lock")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    monkeypatch.setattr("apps.shared.live_app.service.read_app_file", lambda **_: "<html>old</html>")

    def _raise_lock_timeout(**_):
        raise LiveAppWriteLockTimeoutError("locked")

    monkeypatch.setattr("apps.shared.live_app.service.write_app_file", _raise_lock_timeout)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    with pytest.raises(ValidationError) as exc:
        await service.write_file(live_app.id, "entry.html", "<html>new</html>")

    assert exc.value.details["code"] == "APP_CONFLICT_LOCKED"
    assert exc.value.details["app_id"] == live_app.id


@pytest.mark.asyncio
async def test_list_read_write_file_flow(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_files", slug="tenant_live_app_service_files", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_files_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_files")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    write_result = await service.write_file(live_app.id, "src/components/table.js", "export const x = 1;")
    assert write_result["updated"] is True

    read_result = await service.read_file(live_app.id, "src/components/table.js")
    assert read_result["content"] == "export const x = 1;"

    files_result = await service.list_files(live_app.id)
    assert "src/components/table.js" in files_result["files"]


@pytest.mark.asyncio
async def test_write_file_noop_skips_commit(async_db_session, monkeypatch, tmp_path: Path):
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

    commit_calls = {"count": 0}

    def _fake_commit(**_):
        commit_calls["count"] += 1
        return True

    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", _fake_commit)

    tenant = Tenant(name="tenant_live_app_service_noop", slug="tenant_live_app_service_noop", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_noop_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_noop")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    first = await service.write_file(live_app.id, "src/main.js", "console.log(1)")
    second = await service.write_file(live_app.id, "src/main.js", "console.log(1)")

    assert first["updated"] is True
    assert second["updated"] is False
    assert second["committed"] is False
    assert commit_calls["count"] == 0


@pytest.mark.asyncio
async def test_write_file_writes_audit_event(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_audit_file", slug="tenant_live_app_service_audit_file", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_audit_file_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_audit_file")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    calls: list[dict] = []

    async def _fake_add_audit_event(**kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_audit_event)
    await service.write_file(live_app.id, "src/audit.js", "console.log('audit')", actor_user_id=user.id)

    assert len(calls) == 1
    assert calls[0]["actor_user_id"] == user.id
    assert calls[0]["event_type"] == "live_app.file.write"
    assert calls[0]["payload"]["updated"] is True
    assert calls[0]["payload"]["path"] == "src/audit.js"


@pytest.mark.asyncio
async def test_read_file_invalid_path_raises_validation_error(async_db_session):
    tenant = Tenant(name="tenant_live_app_service_path", slug="tenant_live_app_service_path", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_path_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_path")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    with pytest.raises(ValidationError) as exc:
        await service.read_file(live_app.id, "../../etc/passwd")
    assert exc.value.details["code"] == "APP_INVALID_FILE_PATH"


@pytest.mark.asyncio
async def test_read_file_not_found_maps_to_resource_not_found(async_db_session):
    tenant = Tenant(name="tenant_live_app_service_notfound", slug="tenant_live_app_service_notfound", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_notfound_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_notfound")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    with pytest.raises(ResourceNotFoundError):
        await service.read_file(live_app.id, "src/missing.js")


@pytest.mark.asyncio
async def test_query_data_success(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_query", slug="tenant_live_app_service_query", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_query_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_query")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    live_app.data_source_id = 1

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        assert app_id == live_app.id
        assert tenant_id == tenant.id
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)

    async def _fake_query_data(**kwargs):
        assert kwargs["data_source_id"] is not None
        return pd.DataFrame([{"id": 1, "name": "A"}])

    class _FakeDataExecutor:
        async def query_data(self, **kwargs):
            return await _fake_query_data(**kwargs)

    fake_data_executor = _FakeDataExecutor()

    async def _fake_add_event(**_):
        return None

    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_event)

    monkeypatch.setattr(service, "data_executor", fake_data_executor)
    result = await service.query_data(live_app.id, f"SELECT id, name FROM app_{live_app.id}.orders")
    assert result["row_count"] == 1
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [[1, "A"]]


@pytest.mark.asyncio
async def test_query_data_rejects_non_select(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_query_invalid", slug="tenant_live_app_service_query_invalid", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_query_invalid_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_query_invalid")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    live_app.data_source_id = 1

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        assert app_id == live_app.id
        assert tenant_id == tenant.id
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)

    with pytest.raises(ValidationError) as exc:
        await service.query_data(live_app.id, f"DELETE FROM app_{live_app.id}.orders")
    assert exc.value.details["code"] == "APP_INVALID_SQL"


@pytest.mark.asyncio
async def test_query_data_rejects_namespace_violation(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_query_scope", slug="tenant_live_app_service_query_scope", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_query_scope_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_query_scope")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    live_app.data_source_id = 1

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        assert app_id == live_app.id
        assert tenant_id == tenant.id
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)

    with pytest.raises(ValidationError) as exc:
        await service.query_data(live_app.id, "SELECT * FROM public.users")
    assert exc.value.details["code"] == "APP_NAMESPACE_VIOLATION"


@pytest.mark.asyncio
async def test_mutate_data_insert_success(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_mutate", slug="tenant_live_app_service_mutate", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_mutate_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_mutate")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    live_app.data_source_id = 1

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        assert app_id == live_app.id
        assert tenant_id == tenant.id
        return live_app

    async def _fake_insert_rows(**kwargs):
        assert kwargs["data_source_id"] == 1
        assert kwargs["full_table_name"] == f"app_{live_app.id}.orders"
        assert len(kwargs["rows"]) == 1
        return 1

    async def _fake_add_event(**_):
        return None

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    monkeypatch.setattr(service.data_executor, "insert_rows", _fake_insert_rows)
    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_event)

    result = await service.mutate_data(
        live_app.id,
        "insert",
        "orders",
        {"id": 1, "name": "n"},
        actor_user_id=user.id,
    )
    assert result["affected_rows"] == 1
    assert result["table"] == f"app_{live_app.id}.orders"


@pytest.mark.asyncio
async def test_mutate_data_rejects_non_insert(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_mutate_op", slug="tenant_live_app_service_mutate_op", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_mutate_op_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_mutate_op")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    live_app.data_source_id = 1

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    with pytest.raises(ValidationError) as exc:
        await service.mutate_data(live_app.id, "update", "orders", {"id": 1})
    assert exc.value.details["code"] == "APP_INVALID_SQL"


@pytest.mark.asyncio
async def test_mutate_data_rejects_namespace_violation(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_mutate_scope", slug="tenant_live_app_service_mutate_scope", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_mutate_scope_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_mutate_scope")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    live_app.data_source_id = 1

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    with pytest.raises(ValidationError) as exc:
        await service.mutate_data(live_app.id, "insert", "public.orders", {"id": 1})
    assert exc.value.details["code"] == "APP_NAMESPACE_VIOLATION"


@pytest.mark.asyncio
async def test_import_data_success(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_import", slug="tenant_live_app_service_import", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_import_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_import")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    async def _fake_import_csv(**kwargs):
        assert kwargs["full_table_name"] == f"app_{live_app.id}.orders"
        return 1

    async def _fake_add_event(**_):
        return None

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    monkeypatch.setattr(service.data_executor, "import_csv", _fake_import_csv)
    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_event)

    result = await service.import_data(
        live_app.id,
        table="orders",
        mode="append",
        file_name="import.csv",
        file_content=b"id,name\n1,a\n",
        actor_user_id=user.id,
    )
    assert result["imported_rows"] == 1
    assert result["table"] == f"app_{live_app.id}.orders"


@pytest.mark.asyncio
async def test_import_data_rejects_cross_namespace(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_import_scope", slug="tenant_live_app_service_import_scope", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_service_import_scope_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_import_scope")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    with pytest.raises(ValidationError) as exc:
        await service.import_data(
            live_app.id,
            table="public.orders",
            mode="append",
            file_name="import.csv",
            file_content=b"id,name\n1,a\n",
        )
    assert exc.value.details["code"] == "APP_IMPORT_TARGET_FORBIDDEN"


@pytest.mark.asyncio
async def test_list_migrations_includes_applied_status(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_migrations", slug="tenant_live_app_service_migrations", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_migrations_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_migrations")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(
        live_app.id,
        "migrations/001_init.up.sql",
        "CREATE TABLE t(id INT);",
        environment="dev",
        actor_user_id=user.id,
    )

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    async def _fake_list_applied_migrations(**kwargs):
        return [{"name": "001_init", "checksum": "abc", "applied_at": "2026-03-31T00:00:00Z"}]

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    monkeypatch.setattr(service.data_executor, "list_applied_migrations", _fake_list_applied_migrations)
    result = await service.list_migrations(live_app.id, environment="dev")

    assert result["app_id"] == live_app.id
    assert len(result["migrations"]) == 1
    assert result["migrations"][0]["name"] == "001_init"
    assert result["migrations"][0]["applied"] is True
    assert result["migrations"][0]["applied_at"] == "2026-03-31T00:00:00Z"


@pytest.mark.asyncio
async def test_apply_migration_success(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_apply", slug="tenant_live_app_service_apply", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_apply_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_apply")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(
        live_app.id,
        "migrations/001_init.up.sql",
        "CREATE TABLE t(id INT);",
        environment="dev",
        actor_user_id=user.id,
    )

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    async def _fake_apply_migration(**kwargs):
        assert kwargs["schema_name"] == f"app_{live_app.id}_dev"
        assert kwargs["migration_name"] == "001_init"
        assert kwargs["up_sql"].startswith("CREATE TABLE")
        return {"applied": True, "reason": "applied"}

    async def _fake_add_event(**_):
        return None

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    monkeypatch.setattr(service.data_executor, "apply_migration", _fake_apply_migration)
    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_event)
    result = await service.apply_migration(live_app.id, "001_init", environment="dev", actor_user_id=user.id)

    assert result["applied"] is True
    assert result["migration"] == "001_init"


@pytest.mark.asyncio
async def test_apply_migration_rejects_missing_file(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_apply_missing", slug="tenant_live_app_service_apply_missing", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_apply_missing_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_apply_missing")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    with pytest.raises(ValidationError) as exc:
        await service.apply_migration(live_app.id, "999_missing", environment="dev", actor_user_id=user.id)
    assert exc.value.details["code"] == "APP_MIGRATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_rollback_migration_success(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_rollback", slug="tenant_live_app_service_rollback", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_rollback_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_rollback")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(
        live_app.id,
        "migrations/001_init.up.sql",
        "CREATE TABLE t(id INT);",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.write_file(
        live_app.id,
        "migrations/001_init.down.sql",
        "DROP TABLE IF EXISTS t;",
        environment="dev",
        actor_user_id=user.id,
    )

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    async def _fake_rollback_migration(**kwargs):
        assert kwargs["migration_name"] == "001_init"
        assert kwargs["down_sql"].startswith("DROP TABLE")
        return {"rolled_back": True, "reason": "rolled_back"}

    async def _fake_add_event(**_):
        return None

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    monkeypatch.setattr(service.data_executor, "rollback_migration", _fake_rollback_migration)
    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_event)

    result = await service.rollback_migration(live_app.id, "001_init", environment="dev", actor_user_id=user.id)
    assert result["rolled_back"] is True
    assert result["migration"] == "001_init"


@pytest.mark.asyncio
async def test_rollback_migration_rejects_missing_down_sql(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(
        name="tenant_live_app_service_rollback_missing", slug="tenant_live_app_service_rollback_missing", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_rollback_missing_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_rollback_missing")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(
        live_app.id,
        "migrations/001_init.up.sql",
        "CREATE TABLE t(id INT);",
        environment="dev",
        actor_user_id=user.id,
    )

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    with pytest.raises(ValidationError) as exc:
        await service.rollback_migration(live_app.id, "001_init", environment="dev", actor_user_id=user.id)
    assert exc.value.details["code"] == "APP_MIGRATION_DOWN_MISSING"


@pytest.mark.asyncio
async def test_list_migrations_rejects_non_contiguous_sequences(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_order", slug="tenant_live_app_service_order", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_order_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_order")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(
        live_app.id,
        "migrations/001_init.up.sql",
        "CREATE TABLE t(id INT);",
        environment="dev",
        actor_user_id=user.id,
    )
    await service.write_file(
        live_app.id,
        "migrations/003_add_idx.up.sql",
        "CREATE INDEX i ON t(id);",
        environment="dev",
        actor_user_id=user.id,
    )

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    with pytest.raises(ValidationError) as exc:
        await service.list_migrations(live_app.id, environment="dev")
    assert exc.value.details["code"] == "APP_MIGRATION_ORDER_INVALID"


@pytest.mark.asyncio
async def test_create_migration_writes_files_and_commits(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_create_mig", slug="tenant_live_app_service_create_mig", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_create_mig_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_create_mig")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = await service.create_migration(
        live_app.id,
        "001_init",
        "CREATE TABLE t(id INT);",
        environment="dev",
        down_sql="DROP TABLE IF EXISTS t;",
        actor_user_id=user.id,
    )
    assert result["created"] is True
    assert (
        tmp_path
        / "tenants"
        / f"tenant_{tenant.id}"
        / "apps"
        / "live_apps"
        / f"app_{live_app.id}"
        / "env"
        / "dev"
        / "migrations"
        / "001_init.up.sql"
    ).exists()
    assert (
        tmp_path
        / "tenants"
        / f"tenant_{tenant.id}"
        / "apps"
        / "live_apps"
        / f"app_{live_app.id}"
        / "env"
        / "dev"
        / "migrations"
        / "001_init.down.sql"
    ).exists()


@pytest.mark.asyncio
async def test_remove_migration_deletes_files(async_db_session, monkeypatch, tmp_path: Path):
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
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    tenant = Tenant(name="tenant_live_app_service_remove_mig", slug="tenant_live_app_service_remove_mig", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_remove_mig_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_remove_mig")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.create_migration(
        live_app.id,
        "001_init",
        "CREATE TABLE t(id INT);",
        environment="dev",
        down_sql="DROP TABLE IF EXISTS t;",
        actor_user_id=user.id,
    )
    result = await service.remove_migration(live_app.id, "001_init", environment="dev", actor_user_id=user.id)

    app_root = (
        tmp_path / "tenants" / f"tenant_{tenant.id}" / "apps" / "live_apps" / f"app_{live_app.id}" / "env" / "dev"
    )
    assert result["removed"] is True
    assert not (app_root / "migrations" / "001_init.up.sql").exists()
    assert not (app_root / "migrations" / "001_init.down.sql").exists()


@pytest.mark.asyncio
async def test_commit_changes_commits_once(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_commit", slug="tenant_live_app_service_commit", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_commit_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_commit")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    async def _fake_get_for_tenant(app_id: int, tenant_id: int):
        return live_app

    async def _fake_add_event(**_):
        return None

    monkeypatch.setattr(service.repo, "get_for_tenant", _fake_get_for_tenant)
    monkeypatch.setattr(service.audit_repo, "add_event", _fake_add_event)
    monkeypatch.setattr("apps.shared.live_app.service.commit_app_changes", lambda **_: True)

    result = await service.commit_changes(
        live_app.id, environment="dev", commit_message="round commit", actor_user_id=user.id
    )
    assert result["committed"] is True
    assert result["environment"] == "dev"


@pytest.mark.asyncio
async def test_commit_changes_rejects_non_dev_environment(async_db_session):
    tenant = Tenant(
        name="tenant_live_app_service_commit_non_dev", slug="tenant_live_app_service_commit_non_dev", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_commit_non_dev_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_commit_non_dev")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ValidationError) as exc:
        await service.commit_changes(live_app.id, environment="test", actor_user_id=user.id)
    assert exc.value.details["code"] == "APP_GIT_DEV_ONLY"


@pytest.mark.asyncio
async def test_promote_environment_rejects_invalid_transition(async_db_session):
    tenant = Tenant(
        name="tenant_live_app_service_promote_invalid", slug="tenant_live_app_service_promote_invalid", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_invalid_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_invalid")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    with pytest.raises(ValidationError) as exc:
        await service.promote_environment(
            live_app.id,
            from_environment="dev",
            to_environment="prod",
            actor_user_id=user.id,
        )
    assert exc.value.details["code"] == "APP_INVALID_ENV_PROMOTION"


@pytest.mark.asyncio
async def test_promote_environment_rejects_missing_source_commit(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_promote_missing_commit",
        slug="tenant_live_app_service_promote_missing_commit",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_missing_commit_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_missing_commit")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.get_latest_commit_for_app_environment", lambda **_: None)
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: True)

    with pytest.raises(ValidationError) as exc:
        await service.promote_environment(
            live_app.id,
            from_environment="dev",
            to_environment="test",
            actor_user_id=user.id,
        )
    assert exc.value.details["code"] == "APP_PROMOTION_SOURCE_COMMIT_NOT_FOUND"


@pytest.mark.asyncio
async def test_promote_environment_syncs_files_and_removes_stale(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(
        name="tenant_live_app_service_promote_sync", slug="tenant_live_app_service_promote_sync", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_sync_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_sync")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service.write_file(
        live_app.id,
        "src/old.js",
        "console.log('stale-test')",
        environment="test",
        actor_user_id=user.id,
    )
    monkeypatch.setattr("apps.shared.live_app.service.get_latest_commit_for_app_environment", lambda **_: "abc123")
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: True)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_files_at_commit",
        lambda **_: ["entry.html", "src/main.js"],
    )

    synced_files = {"entry.html": "<html>from-commit</html>", "src/main.js": "console.log('from-commit')"}
    fake_target_commit = "target_commit_abc"

    def _fake_sync(**kwargs):
        from apps.shared.live_app.workspace import get_app_path

        target_root = get_app_path(
            kwargs["tenant_id"], kwargs["app_id"], environment=kwargs["target_environment"], create=True
        )
        import shutil

        for child in target_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for rel_path, content in synced_files.items():
            dest = target_root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        return fake_target_commit

    monkeypatch.setattr("apps.shared.live_app.service.sync_environment_from_commit", _fake_sync)

    async def _fake_apply_migration(**_):
        return {"applied": False, "reason": "already_applied"}

    monkeypatch.setattr(service.data_executor, "apply_migration", _fake_apply_migration)

    result = await service.promote_environment(
        live_app.id,
        from_environment="dev",
        to_environment="test",
        actor_user_id=user.id,
    )

    promoted_file = await service.read_file(live_app.id, "src/main.js", environment="test")
    with pytest.raises(ResourceNotFoundError):
        await service.read_file(live_app.id, "src/old.js", environment="test")

    assert result["from_environment"] == "dev"
    assert result["to_environment"] == "test"
    assert result["promoted_files"] >= 1
    assert "src/old.js" in result["removed_files"]
    assert result["source_commit"] == "abc123"
    assert result["migrations"]["enabled"] is True
    assert result["migrations"]["reason"] == "applied"
    assert result["deployment_state"]["test"] == "abc123"
    assert promoted_file["content"] == "console.log('from-commit')"


@pytest.mark.asyncio
async def test_promote_environment_applies_target_migrations(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(
        name="tenant_live_app_service_promote_migrate", slug="tenant_live_app_service_promote_migrate", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_migrate_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_migrate")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.get_latest_commit_for_app_environment", lambda **_: "def456")
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: True)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_files_at_commit",
        lambda **_: ["entry.html", "migrations/001_init.up.sql"],
    )

    fake_target_commit = "target_commit_def"

    def _fake_sync(**kwargs):
        from apps.shared.live_app.workspace import get_app_path

        target_root = get_app_path(
            kwargs["tenant_id"], kwargs["app_id"], environment=kwargs["target_environment"], create=True
        )
        mig_dir = target_root / "migrations"
        mig_dir.mkdir(parents=True, exist_ok=True)
        (mig_dir / "001_init.up.sql").write_text("CREATE TABLE IF NOT EXISTS t(id INT);", encoding="utf-8")
        return fake_target_commit

    monkeypatch.setattr("apps.shared.live_app.service.sync_environment_from_commit", _fake_sync)

    applied_calls: list[dict] = []

    async def _fake_apply_migration(**kwargs):
        applied_calls.append(kwargs)
        return {"applied": True, "reason": "applied"}

    monkeypatch.setattr(service.data_executor, "apply_migration", _fake_apply_migration)

    result = await service.promote_environment(
        live_app.id,
        from_environment="dev",
        to_environment="test",
        actor_user_id=user.id,
    )

    assert result["source_commit"] == "def456"
    assert result["migrations"]["enabled"] is True
    assert result["migrations"]["applied"] == ["001_init"]
    assert result["migrations"]["schema"] == f"app_{live_app.id}_test"
    assert result["deployment_state"]["test"] == "def456"
    assert len(applied_calls) == 1
    assert applied_calls[0]["schema_name"] == f"app_{live_app.id}_test"


@pytest.mark.asyncio
async def test_promote_environment_dry_run_skips_writes_and_returns_preview(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_promote_dryrun", slug="tenant_live_app_service_promote_dryrun", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_dryrun_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_dryrun")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.get_latest_commit_for_app_environment", lambda **_: "dry123")
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: True)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_files_at_commit",
        lambda **_: ["entry.html", "migrations/001_init.up.sql"],
    )
    monkeypatch.setattr("apps.shared.live_app.service.list_app_files", lambda **_: ["src/stale.js"])
    monkeypatch.setattr(
        "apps.shared.live_app.service.sync_environment_from_commit",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("sync_environment_from_commit should not be called in dry_run")
        ),
    )

    async def _fake_list_applied_migrations(**_):
        return []

    monkeypatch.setattr(service.data_executor, "list_applied_migrations", _fake_list_applied_migrations)

    result = await service.promote_environment(
        live_app.id,
        from_environment="dev",
        to_environment="test",
        dry_run=True,
        actor_user_id=user.id,
    )

    assert result["dry_run"] is True
    assert result["source_commit"] == "dry123"
    assert result["promoted_files"] == 2
    assert result["removed_files"] == ["src/stale.js"]
    assert result["migrations"]["reason"] == "dry_run"
    assert result["migrations"]["pending"] == ["001_init"]
    assert result["deployment_state"]["test"] == "dry123"
    assert live_app.app_config.get("deployed_commits") is None


@pytest.mark.asyncio
async def test_promote_environment_failed_migration_does_not_update_deployment_state(
    async_db_session, monkeypatch, tmp_path: Path
):
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

    tenant = Tenant(
        name="tenant_live_app_service_promote_fail", slug="tenant_live_app_service_promote_fail", config=None
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_fail_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_fail")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.get_latest_commit_for_app_environment", lambda **_: "bad999")
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: True)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_files_at_commit",
        lambda **_: ["entry.html", "migrations/001_init.up.sql"],
    )

    def _fake_sync(**kwargs):
        from apps.shared.live_app.workspace import get_app_path

        target_root = get_app_path(
            kwargs["tenant_id"], kwargs["app_id"], environment=kwargs["target_environment"], create=True
        )
        mig_dir = target_root / "migrations"
        mig_dir.mkdir(parents=True, exist_ok=True)
        (mig_dir / "001_init.up.sql").write_text("CREATE TABLE t(id INT);", encoding="utf-8")
        return "target_commit_bad"

    monkeypatch.setattr("apps.shared.live_app.service.sync_environment_from_commit", _fake_sync)

    async def _fail_apply_migration(**_):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.data_executor, "apply_migration", _fail_apply_migration)

    with pytest.raises(ValidationError) as exc:
        await service.promote_environment(
            live_app.id,
            from_environment="dev",
            to_environment="test",
            actor_user_id=user.id,
        )
    assert exc.value.details["code"] == "APP_MIGRATION_APPLY_FAILED"
    assert live_app.app_config.get("deployed_commits") is None


@pytest.mark.asyncio
async def test_promote_environment_rejects_commit_not_in_dev_history(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_promote_bad_history",
        slug="tenant_live_app_service_promote_bad_history",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_bad_history_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_bad_history")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.get_latest_commit_for_app_environment", lambda **_: "deadbeef")
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: False)

    with pytest.raises(ValidationError) as exc:
        await service.promote_environment(
            live_app.id,
            from_environment="dev",
            to_environment="test",
            actor_user_id=user.id,
        )
    assert exc.value.details["code"] == "APP_PROMOTION_SOURCE_COMMIT_NOT_IN_DEV_HISTORY"


@pytest.mark.asyncio
async def test_promote_environment_test_to_prod_requires_explicit_source_commit(async_db_session):
    tenant = Tenant(
        name="tenant_live_app_service_promote_explicit_commit",
        slug="tenant_live_app_service_promote_explicit_commit",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_explicit_commit_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promote_explicit_commit")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)
    live_app.data_source_id = 1

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    with pytest.raises(ValidationError) as exc:
        await service.promote_environment(
            live_app.id,
            from_environment="test",
            to_environment="prod",
            actor_user_id=user.id,
        )
    assert exc.value.details["code"] == "APP_PROMOTION_SOURCE_COMMIT_REQUIRED"


@pytest.mark.asyncio
async def test_promote_environment_test_to_prod_success_with_explicit_commit(async_db_session, monkeypatch):
    tenant = Tenant(
        name="tenant_live_app_service_promote_test_prod_ok",
        slug="tenant_live_app_service_promote_test_prod_ok",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_test_prod_ok_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(
        tenant_id=tenant.id,
        owner_id=user.id,
        name="service_app_promote_test_prod_ok",
        data_source_id=1,
        app_config={"deployed_commits": {"test": "abc123"}},
    )
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.is_commit_in_app_environment_history", lambda **_: True)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_files_at_commit",
        lambda **_: ["entry.html", "src/main.js"],
    )
    fake_target_commit = "target_commit_prod"
    monkeypatch.setattr("apps.shared.live_app.service.sync_environment_from_commit", lambda **_: fake_target_commit)

    result = await service.promote_environment(
        live_app.id,
        from_environment="test",
        to_environment="prod",
        source_commit="abc123",
        actor_user_id=user.id,
    )

    assert result["from_environment"] == "test"
    assert result["to_environment"] == "prod"
    assert result["source_commit"] == "abc123"
    assert result["deployment_state"]["prod"] == "abc123"


@pytest.mark.asyncio
async def test_promote_environment_real_git_dev_test_prod_flow(async_db_session, monkeypatch, tmp_path: Path):
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

    tenant = Tenant(
        name="tenant_live_app_service_promote_real_git",
        slug="tenant_live_app_service_promote_real_git",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promote_real_git_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_promote_real_git",
        type="postgres",
        managed=True,
        config={},
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    async def _fake_ensure_schema(self, *, data_source_id: int, schema_name: str):
        return None

    monkeypatch.setattr("apps.shared.live_app.data_executor.LiveAppDataExecutor.ensure_schema", _fake_ensure_schema)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    created = (
        await service.create_app_with_artifact(name="real_git_flow_app", owner_id=user.id, data_source_id=managed_ds.id)
    ).app

    await service.write_file(
        created.app_id,
        "src/main.js",
        "console.log('dev version 1')",
        environment="dev",
        actor_user_id=user.id,
    )
    committed = await service.commit_changes(
        created.app_id,
        environment="dev",
        commit_message="dev baseline",
        actor_user_id=user.id,
    )
    assert committed["committed"] is True

    commit_sha = get_latest_commit_for_app_environment(tenant_id=tenant.id, app_id=created.app_id, environment="dev")
    assert commit_sha is not None

    promote_to_test = await service.promote_environment(
        created.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=commit_sha,
        actor_user_id=user.id,
    )
    assert promote_to_test["deployment_state"]["test"] == commit_sha

    promote_to_prod = await service.promote_environment(
        created.app_id,
        from_environment="test",
        to_environment="prod",
        source_commit=commit_sha,
        actor_user_id=user.id,
    )
    assert promote_to_prod["deployment_state"]["prod"] == commit_sha

    prod_file = await service.read_file(created.app_id, "src/main.js", environment="prod")
    assert prod_file["content"] == "console.log('dev version 1')"


@pytest.mark.asyncio
async def test_promote_environment_warns_on_uncommitted_dev_changes(async_db_session, monkeypatch, tmp_path: Path):
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

    async def _fake_ensure_schema(self, *, data_source_id: int, schema_name: str):
        return None

    monkeypatch.setattr("apps.shared.live_app.data_executor.LiveAppDataExecutor.ensure_schema", _fake_ensure_schema)

    tenant = Tenant(
        name="tenant_promote_uncommitted_warn",
        slug="tenant_promote_uncommitted_warn",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="promote_uncommitted_warn_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    managed_ds = DataSource(
        tenant_id=tenant.id,
        name="managed_ds_uncommitted_warn",
        type="postgres",
        managed=True,
        config={},
        owner_id=user.id,
    )
    async_db_session.add(managed_ds)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    created = (
        await service.create_app_with_artifact(
            name="uncommitted_warn_app", owner_id=user.id, data_source_id=managed_ds.id
        )
    ).app

    await service.write_file(
        created.app_id, "src/main.js", "console.log('v1')", environment="dev", actor_user_id=user.id
    )
    await service.commit_changes(created.app_id, environment="dev", commit_message="v1", actor_user_id=user.id)
    commit_sha = get_latest_commit_for_app_environment(tenant_id=tenant.id, app_id=created.app_id, environment="dev")

    # Clean dev: no warnings expected
    result_clean = await service.promote_environment(
        created.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=commit_sha,
        actor_user_id=user.id,
    )
    assert "warnings" not in result_clean

    # Now modify dev without committing
    await service.write_file(
        created.app_id, "src/main.js", "console.log('v2')", environment="dev", actor_user_id=user.id
    )

    result_dirty = await service.promote_environment(
        created.app_id,
        from_environment="dev",
        to_environment="test",
        source_commit=commit_sha,
        actor_user_id=user.id,
    )
    assert "warnings" in result_dirty
    assert any("uncommitted" in w.lower() for w in result_dirty["warnings"])


@pytest.mark.asyncio
async def test_get_deployment_state_returns_current_pointers(async_db_session):
    tenant = Tenant(name="tenant_live_app_service_state", slug="tenant_live_app_service_state", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_state_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(
        tenant_id=tenant.id,
        owner_id=user.id,
        name="service_app_state",
        app_config={"deployed_commits": {"dev": "d1", "test": "t1"}},
    )
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = await service.get_deployment_state(live_app.id)
    assert result["app_id"] == live_app.id
    assert result["deployment_state"]["dev"] == "d1"
    assert result["deployment_state"]["test"] == "t1"
    assert result["deployment_state"]["prod"] is None


@pytest.mark.asyncio
async def test_diff_environments_returns_changed_files(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_diff", slug="tenant_live_app_service_diff", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_diff_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(
        tenant_id=tenant.id,
        owner_id=user.id,
        name="service_app_diff",
        app_config={"deployed_commits": {"dev": "d1", "prod": "p1"}},
    )
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr("apps.shared.live_app.service.ensure_entry_file", lambda **_: None)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_files",
        lambda **kwargs: ["entry.html", "src/main.js"]
        if kwargs["environment"] == "dev"
        else ["entry.html", "src/main.js", "src/new.js"],
    )
    monkeypatch.setattr(
        "apps.shared.live_app.service.read_app_file",
        lambda **kwargs: (
            "<html>dev</html>"
            if kwargs["relative_path"] == "entry.html" and kwargs["environment"] == "dev"
            else "<html>prod</html>"
            if kwargs["relative_path"] == "entry.html"
            else "console.log('same')"
        ),
    )

    result = await service.diff_environments(live_app.id, from_environment="dev", to_environment="prod")
    assert result["from_environment"] == "dev"
    assert result["to_environment"] == "prod"
    assert result["same_deployed_commit"] is False
    assert result["files"]["only_in_to"] == ["src/new.js"]
    assert result["summary"]["changed_count"] == 1
    assert result["summary"]["in_sync"] is False


@pytest.mark.asyncio
async def test_diff_environments_rejects_same_environment(async_db_session):
    tenant = Tenant(name="tenant_live_app_service_diff_same", slug="tenant_live_app_service_diff_same", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_diff_same_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_diff_same")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ValidationError) as exc:
        await service.diff_environments(live_app.id, from_environment="dev", to_environment="dev")
    assert exc.value.details["code"] == "APP_ENV_DIFF_INVALID_ENV"


@pytest.mark.asyncio
async def test_list_commits_returns_workspace_commits(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_commits", slug="tenant_live_app_service_commits", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_commits_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_commits")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    monkeypatch.setattr(
        "apps.shared.live_app.service.list_app_commits_for_environment",
        lambda **_: [{"sha": "abc", "timestamp_unix": 1, "message": "c1"}],
    )

    result = await service.list_commits(live_app.id, environment="dev", limit=10)
    assert result["app_id"] == live_app.id
    assert result["environment"] == "dev"
    assert result["commits"][0]["sha"] == "abc"


@pytest.mark.asyncio
async def test_list_commits_rejects_non_dev_environment(async_db_session):
    tenant = Tenant(
        name="tenant_live_app_service_list_commits_non_dev",
        slug="tenant_live_app_service_list_commits_non_dev",
        config=None,
    )
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_list_commits_non_dev_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_list_commits_non_dev")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ValidationError) as exc:
        await service.list_commits(live_app.id, environment="prod")
    assert exc.value.details["code"] == "APP_GIT_DEV_ONLY"


@pytest.mark.asyncio
async def test_list_promotions_returns_audit_payloads(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_live_app_service_promotions", slug="tenant_live_app_service_promotions", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="live_app_service_promotions_user",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    live_app = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="service_app_promotions")
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    async def _fake_list_events(**_):
        return [
            SimpleNamespace(
                created_at=None,
                actor_user_id=user.id,
                payload={
                    "app_id": live_app.id,
                    "from_environment": "dev",
                    "to_environment": "test",
                    "source_commit": "abc",
                    "promoted_files": 3,
                    "removed_files": [],
                    "migrations": {"enabled": True},
                },
            ),
            SimpleNamespace(created_at=None, actor_user_id=user.id, payload={"app_id": 999}),
        ]

    monkeypatch.setattr(service.audit_repo, "list_events", _fake_list_events)
    result = await service.list_promotions(live_app.id, limit=10)
    assert result["app_id"] == live_app.id
    assert len(result["promotions"]) == 1
    assert result["promotions"][0]["source_commit"] == "abc"
