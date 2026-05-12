"""Integration contract tests for live app v1 runtime API.

These tests validate the API surface that the live app SDK depends on at
runtime (from inside the iframe).  They use a real Postgres via testcontainers,
seed real data, and assert actual response shapes.

The contracted route list and SDK method list are declared inline here as the
single source of truth.  Adding or removing entries produces a visible PR diff.

Only runtime routes (SDK-facing) are contracted.  Management routes (portal/
agent internal) are NOT included and can evolve freely.
"""

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

# ---------------------------------------------------------------------------
# v1 contract surface — the single source of truth
# ---------------------------------------------------------------------------

V1_CONTRACTED_ROUTES = [
    # Serving (entry, embed, static assets, SDK, vendor libs)
    "GET  /apps/{app_id}/{environment}/entry",
    "GET  /apps/{app_id}/{environment}/embed",
    "GET  /apps/{app_id}/{environment}/{asset_path}",
    "GET  /apps/sdk/lq-sdk.v{sdk_version}.js",
    "GET  /apps/sdk/vendor/{filename}",
    # Data APIs (SDK calls these from the iframe)
    "POST /apps/v1/{app_id}/{environment}/data/query",
    "POST /apps/v1/{app_id}/{environment}/data/mutate",
    "POST /apps/v1/{app_id}/{environment}/data/import",
]

V1_SDK_CLIENT_METHODS = [
    "query",
    "mutateInsert",
    "mutateUpdateById",
    "mutateUpdateRows",
    "mutateDeleteById",
    "importCsv",
    "setAppId",
    "setEnvironment",
]

V1_MUTATE_OPERATIONS = ["insert", "update", "update_by_id", "delete_by_id"]

V1_ERROR_CODES = [
    "APP_NOT_FOUND",
    "APP_PERMISSION_DENIED",
    "APP_NAMESPACE_VIOLATION",
    "APP_INVALID_SQL",
    "APP_IMPORT_TARGET_FORBIDDEN",
    "APP_RUNTIME_BROKEN",
    "APP_CONFLICT_LOCKED",
    "APP_INVALID_ENVIRONMENT",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pg_config_from_session(session: AsyncSession) -> dict:
    url = session.bind.engine.url
    return {
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
        "password": url.password,
    }


def _assert_success_envelope(payload: dict):
    assert "data" in payload, f"Missing 'data' key in response: {payload.keys()}"
    assert "meta" in payload, f"Missing 'meta' key in response: {payload.keys()}"
    meta = payload["meta"]
    assert "request_id" in meta
    assert "api_version" in meta
    assert meta["api_version"] == "v1"


def _assert_error_envelope(payload: dict):
    for key in ("code", "message", "request_id"):
        assert key in payload, f"Missing '{key}' in error response: {payload.keys()}"


# ---------------------------------------------------------------------------
# Fixture: seed a live app with a real table for data API tests
# ---------------------------------------------------------------------------


@pytest.fixture
def contract_env(async_db_session, monkeypatch, tmp_path: Path, request):
    """Seed tenant + user + datasource + live app with a test table."""
    import asyncio
    from uuid import uuid4

    suffix = uuid4().hex[:8]

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
    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _seed():
        async with test_session_factory() as session:
            tenant = Tenant(name=f"contract_{suffix}", slug=f"contract-{suffix}", config=None)
            session.add(tenant)
            await session.flush()

            user = User(
                username=f"contract_user_{suffix}",
                email=None,
                hashed_password="hashed",
                role="admin",
                tenant_id=tenant.id,
            )
            session.add(user)
            await session.flush()

            ds = DataSource(
                tenant_id=tenant.id,
                name=f"contract_ds_{suffix}",
                type="postgres",
                managed=True,
                config=_pg_config_from_session(session),
                owner_id=user.id,
            )
            session.add(ds)
            await session.flush()

            service = LiveAppService.create(tenant_id=tenant.id, db_session=session)
            app_record = (
                await service.create_app_with_artifact(
                    name=f"contract_app_{suffix}",
                    owner_id=user.id,
                    data_source_id=ds.id,
                )
            ).app

            await service.write_file(
                app_record.app_id,
                "entry.html",
                "<html><head></head><body><h1>Contract Test</h1></body></html>",
                environment="dev",
                actor_user_id=user.id,
            )
            await service.write_file(
                app_record.app_id,
                "static/style.css",
                "body { margin: 0; }",
                environment="dev",
                actor_user_id=user.id,
            )
            await service.commit_changes(
                app_record.app_id,
                environment="dev",
                commit_message="contract test seed",
                actor_user_id=user.id,
            )

            up_sql = (
                "CREATE TABLE IF NOT EXISTS contract_items ("
                "  id SERIAL PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  value INTEGER DEFAULT 0"
                ");"
            )
            down_sql = "DROP TABLE IF EXISTS contract_items;"
            await service.create_migration(
                app_record.app_id,
                migration_name="001_create_contract_items",
                up_sql=up_sql,
                down_sql=down_sql,
                environment="dev",
                actor_user_id=user.id,
            )
            await service.apply_migration(
                app_record.app_id,
                migration_name="001_create_contract_items",
                environment="dev",
                actor_user_id=user.id,
            )

            await session.commit()
            return {
                "tenant_id": tenant.id,
                "user_id": user.id,
                "app_id": app_record.app_id,
                "sdk_version": app_record.sdk_version,
            }

    ctx = asyncio.get_event_loop().run_until_complete(_seed())

    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def override_user():
        return UserDTO(
            id=ctx["user_id"],
            username=f"contract_user_{suffix}",
            role="admin",
            tenant_id=ctx["tenant_id"],
            tenant_name=f"contract-{suffix}",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    ctx["client"] = TestClient(app)
    ctx["engine"] = test_engine
    yield ctx

    app.dependency_overrides.clear()
    asyncio.get_event_loop().run_until_complete(test_engine.dispose())


# ===========================================================================
# Serving contract
# ===========================================================================


def test_contract_entry_serves_html_with_sdk(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].get(f"/apps/{app_id}/dev/entry")

    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    assert "lq-sdk.v" in body, "SDK script tag not injected"
    assert "LQ.createLiveAppClient" in body, "SDK bootstrap not injected"
    assert "Contract Test" in body


def test_contract_embed_serves_html(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].get(f"/apps/{app_id}/dev/embed")

    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_contract_sdk_js_serves_and_contains_client_methods(contract_env):
    sdk_version = contract_env["sdk_version"]
    resp = contract_env["client"].get(f"/apps/sdk/lq-sdk.v{sdk_version}.js")

    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
    assert "immutable" in resp.headers.get("cache-control", "")

    js_content = resp.text
    for method in V1_SDK_CLIENT_METHODS:
        assert method in js_content, f"SDK missing contracted method: {method}"


def test_contract_vendor_asset_serves(contract_env):
    resp = contract_env["client"].get("/apps/sdk/vendor/tailwind-3.4.17.js")
    if resp.status_code == 200:
        assert "javascript" in resp.headers.get("content-type", "")
        assert "immutable" in resp.headers.get("cache-control", "")
    else:
        pytest.skip("Vendor asset not found (may not be committed)")


def test_contract_static_asset_serves(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].get(f"/apps/{app_id}/dev/static/style.css")

    assert resp.status_code == 200
    assert "body" in resp.text


# ===========================================================================
# Data API contract
# ===========================================================================


def test_contract_query_response_shape(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].post(
        f"/apps/v1/{app_id}/dev/data/query",
        json={"sql": "SELECT id, name, value FROM contract_items"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    _assert_success_envelope(payload)

    data = payload["data"]
    for key in ("rows", "columns", "row_count"):
        assert key in data, f"Missing '{key}' in query response data: {data.keys()}"


def test_contract_mutate_insert_response_shape(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].post(
        f"/apps/v1/{app_id}/dev/data/mutate",
        json={"operation": "insert", "table": "contract_items", "data": {"name": "item1", "value": 10}},
    )

    assert resp.status_code == 200
    payload = resp.json()
    _assert_success_envelope(payload)

    data = payload["data"]
    for key in ("operation", "table", "affected_rows"):
        assert key in data, f"Missing '{key}' in mutate response data: {data.keys()}"
    assert data["operation"] == "insert"


def test_contract_mutate_update_by_id_response_shape(contract_env):
    app_id = contract_env["app_id"]
    client = contract_env["client"]

    client.post(
        f"/apps/v1/{app_id}/dev/data/mutate",
        json={"operation": "insert", "table": "contract_items", "data": {"name": "upd_item", "value": 1}},
    )

    query_resp = client.post(
        f"/apps/v1/{app_id}/dev/data/query",
        json={"sql": "SELECT id FROM contract_items WHERE name = 'upd_item' LIMIT 1"},
    )
    row_id = query_resp.json()["data"]["rows"][0][0]

    resp = client.post(
        f"/apps/v1/{app_id}/dev/data/mutate",
        json={"operation": "update_by_id", "table": "contract_items", "data": {"value": 99}, "id": row_id},
    )

    assert resp.status_code == 200
    payload = resp.json()
    _assert_success_envelope(payload)
    assert payload["data"]["operation"] == "update_by_id"
    assert "affected_rows" in payload["data"]


def test_contract_mutate_delete_by_id_response_shape(contract_env):
    app_id = contract_env["app_id"]
    client = contract_env["client"]

    client.post(
        f"/apps/v1/{app_id}/dev/data/mutate",
        json={"operation": "insert", "table": "contract_items", "data": {"name": "del_item", "value": 0}},
    )

    query_resp = client.post(
        f"/apps/v1/{app_id}/dev/data/query",
        json={"sql": "SELECT id FROM contract_items WHERE name = 'del_item' LIMIT 1"},
    )
    row_id = query_resp.json()["data"]["rows"][0][0]

    resp = client.post(
        f"/apps/v1/{app_id}/dev/data/mutate",
        json={"operation": "delete_by_id", "table": "contract_items", "id": row_id},
    )

    assert resp.status_code == 200
    payload = resp.json()
    _assert_success_envelope(payload)
    assert payload["data"]["operation"] == "delete_by_id"
    assert "affected_rows" in payload["data"]


def test_contract_import_csv_response_shape(contract_env):
    app_id = contract_env["app_id"]
    csv_content = b"name,value\nimported_a,100\nimported_b,200\n"

    resp = contract_env["client"].post(
        f"/apps/v1/{app_id}/dev/data/import",
        data={"table": "contract_items", "mode": "append"},
        files={"file": ("import.csv", csv_content, "text/csv")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    _assert_success_envelope(payload)

    data = payload["data"]
    for key in ("table", "imported_rows"):
        assert key in data, f"Missing '{key}' in import response data: {data.keys()}"


# ===========================================================================
# Error envelope contract
# ===========================================================================


def test_contract_error_envelope_invalid_sql(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].post(
        f"/apps/v1/{app_id}/dev/data/query",
        json={"sql": "DROP TABLE contract_items"},
    )

    assert resp.status_code == 400
    payload = resp.json()
    _assert_error_envelope(payload)
    assert payload["code"] in V1_ERROR_CODES


def test_contract_error_envelope_invalid_environment(contract_env):
    app_id = contract_env["app_id"]
    resp = contract_env["client"].get(f"/apps/{app_id}/staging/entry")

    assert resp.status_code == 400
    payload = resp.json()
    _assert_error_envelope(payload)
    assert payload["code"] == "APP_INVALID_ENVIRONMENT"


def test_contract_error_envelope_not_found(contract_env):
    resp = contract_env["client"].post(
        "/apps/v1/999999/dev/data/query",
        json={"sql": "SELECT 1"},
    )

    assert resp.status_code == 404
    payload = resp.json()
    _assert_error_envelope(payload)
    assert payload["code"] == "RESOURCE_NOT_FOUND"


def test_contract_error_unauthenticated():
    """Requests without auth should get 401."""
    app.dependency_overrides.clear()
    try:
        client = TestClient(app)
        resp = client.post("/apps/v1/1/dev/data/query", json={"sql": "SELECT 1"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
