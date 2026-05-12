"""Unit tests for live apps router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.session import get_db
from apps.shared.live_app.adapters import domain_live_app_list_to_dto, domain_live_app_to_dto
from apps.shared.live_app.domain import LiveAppDeploymentState, LiveAppRecord
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import live_apps


@pytest.fixture
def app():
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(live_apps.router)
    api.include_router(live_apps.v1_router)
    return api


@pytest.fixture(autouse=True)
def _stub_live_app_artifact_access(monkeypatch):
    async def _get_app_for_actor(self, app_id: int, *, actor):
        return domain_live_app_to_dto(await self.get_app(app_id=app_id))

    async def _list_apps_for_actor(self, *, actor):
        return domain_live_app_list_to_dto(await self.list_apps(actor.user_id, has_artifacts_manage=False))

    async def _get_entry_page_for_actor(self, app_id: int, *, actor, environment: str = "dev"):
        return await self.get_entry_page(app_id=app_id, environment=environment)

    async def _read_file_for_actor(self, app_id: int, path: str, *, actor, environment: str = "dev"):
        return await self.read_file(app_id=app_id, path=path, environment=environment)

    async def _query_data_for_actor(self, *, app_id: int, actor, sql: str, environment: str = "dev"):
        return await self.query_data(app_id=app_id, sql=sql, environment=environment, actor_user_id=actor.user_id)

    async def _mutate_data_for_actor(
        self,
        *,
        app_id: int,
        actor,
        operation: str,
        table: str,
        data=None,
        where=None,
        row_id=None,
        environment: str = "dev",
    ):
        return await self.mutate_data(
            app_id=app_id,
            operation=operation,
            table=table,
            data=data,
            where=where,
            row_id=row_id,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def _import_data_for_actor(
        self,
        *,
        app_id: int,
        actor,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        environment: str = "dev",
    ):
        return await self.import_data(
            app_id=app_id,
            table=table,
            mode=mode,
            file_name=file_name,
            file_content=file_content,
            environment=environment,
            actor_user_id=actor.user_id,
        )

    async def _diff_environments_for_actor(self, *, app_id: int, actor, from_environment: str, to_environment: str):
        return await self.diff_environments(
            app_id=app_id,
            from_environment=from_environment,
            to_environment=to_environment,
        )

    monkeypatch.setattr(live_apps.LiveAppService, "get_app_for_actor", _get_app_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "list_apps_for_actor", _list_apps_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page_for_actor", _get_entry_page_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "read_file_for_actor", _read_file_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "query_data_for_actor", _query_data_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data_for_actor", _mutate_data_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "import_data_for_actor", _import_data_for_actor)
    monkeypatch.setattr(live_apps.LiveAppService, "diff_environments_for_actor", _diff_environments_for_actor)


def test_get_live_app_entry_renders_html(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        assert app_id == 17
        assert environment == "prod"
        return {
            "app_id": 17,
            "entry_file": "entry.html",
            "sdk_version": "1.0",
            "environment": environment,
            "deployed_commit": "abc123",
            "html": "<html><head></head><body>ok</body></html>",
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/entry")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert '<script src="/api/apps/sdk/lq-sdk.v1.0.js"></script>' in response.text
    assert 'window.LQ.liveApp=window.LQ.createLiveAppClient({appId:17,environment:"prod"});' in response.text
    assert "ok" in response.text


def test_get_live_app_entry_supports_environment_query_param(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        assert app_id == 17
        assert environment == "test"
        return {
            "app_id": 17,
            "entry_file": "entry.html",
            "sdk_version": "1.0",
            "environment": environment,
            "deployed_commit": "def456",
            "html": "<html><head></head><body>test-env</body></html>",
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/test/entry")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "test-env" in response.text


def test_get_live_app_embed_returns_html_for_iframe(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        assert app_id == 17
        assert environment == "prod"
        return {
            "app_id": 17,
            "entry_file": "entry.html",
            "sdk_version": "1.0",
            "environment": environment,
            "deployed_commit": "abc123",
            "html": "<html><head></head><body>embed</body></html>",
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/embed")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert '<script src="/api/apps/sdk/lq-sdk.v1.0.js"></script>' in response.text
    assert 'window.LQ.liveApp=window.LQ.createLiveAppClient({appId:17,environment:"prod"});' in response.text
    assert "embed" in response.text


def test_get_live_app_asset_serves_css_file(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_read_file(self, app_id: int, *, path: str, environment: str = "prod"):
        assert app_id == 17
        assert path == "styles/main.css"
        assert environment == "dev"
        return {"path": path, "content": "body { color: red; }", "updated_at": "2026-01-01T00:00:00Z"}

    monkeypatch.setattr(live_apps.LiveAppService, "read_file", _fake_read_file)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/dev/styles/main.css")

    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")
    assert "color: red" in response.text


def test_get_live_app_asset_disallows_migration_sql_paths(app):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/migrations/001_init.up.sql")
    assert response.status_code == 404


def test_list_live_apps_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=11, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_list_apps(self, user_id, *, has_artifacts_manage=False):
        return [
            LiveAppRecord(
                app_id=31,
                name="sales_app",
                description=None,
                entry_file="entry.html",
                sdk_version="1.0",
                status="draft",
                data_source_id=10,
                owner_name=None,
                deployment_state=LiveAppDeploymentState(),
            ),
            LiveAppRecord(
                app_id=32,
                name="ops_app",
                description=None,
                entry_file="entry.html",
                sdk_version="1.0",
                status="draft",
                data_source_id=11,
                owner_name=None,
                deployment_state=LiveAppDeploymentState(dev="a1"),
            ),
        ]

    monkeypatch.setattr(live_apps.LiveAppService, "list_apps", _fake_list_apps)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["count"] == 2
    assert payload["data"]["apps"][0]["name"] == "sales_app"


def test_get_live_app_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=11, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_app(self, app_id: int):
        assert app_id == 31
        return LiveAppRecord(
            app_id=31,
            name="sales_app",
            description=None,
            entry_file="entry.html",
            sdk_version="1.0",
            status="draft",
            data_source_id=10,
            owner_name=None,
            deployment_state=LiveAppDeploymentState(),
        )

    monkeypatch.setattr(live_apps.LiveAppService, "get_app", _fake_get_app)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/31")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["app_id"] == 31
    assert payload["data"]["name"] == "sales_app"


def test_diff_live_app_environments_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=11, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_diff_environments(self, app_id: int, *, from_environment: str, to_environment: str):
        assert app_id == 31
        assert from_environment == "dev"
        assert to_environment == "prod"
        return {
            "app_id": 31,
            "from_environment": "dev",
            "to_environment": "prod",
            "files": {"only_in_from": [], "only_in_to": ["src/new.js"], "changed": []},
            "summary": {"in_sync": False, "only_in_to_count": 1},
        }

    monkeypatch.setattr(live_apps.LiveAppService, "diff_environments", _fake_diff_environments)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/31/environments/diff?from_environment=dev&to_environment=prod")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["app_id"] == 31
    assert payload["data"]["summary"]["in_sync"] is False
    assert payload["data"]["summary"]["only_in_to_count"] == 1


def test_get_live_app_entry_unknown_sdk_version_returns_404(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        return {
            "app_id": app_id,
            "entry_file": "entry.html",
            "sdk_version": "9.9",
            "environment": environment,
            "html": "<html><head></head><body>ok</body></html>",
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/entry")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "requested_sdk_version",
    [
        "1.0",
    ],
)
def test_get_live_app_entry_sdk_version_matches_injected_script(app, monkeypatch, requested_sdk_version: str):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        return {
            "app_id": app_id,
            "entry_file": "entry.html",
            "sdk_version": requested_sdk_version,
            "environment": environment,
            "html": "<html><head></head><body>ok</body></html>",
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/entry")
    assert response.status_code == 200
    expected_script = f'<script src="/api/apps/sdk/lq-sdk.v{requested_sdk_version}.js"></script>'
    assert expected_script in response.text


def test_inject_sdk_once_idempotent():
    html = "<html><head></head><body>x</body></html>"
    once = live_apps._inject_sdk_once(html, "1.0", app_id=5, environment="dev")
    twice = live_apps._inject_sdk_once(once, "1.0", app_id=5, environment="dev")
    assert once == twice


def test_get_live_app_sdk_returns_javascript(app):
    client = TestClient(app)
    response = client.get("/apps/sdk/lq-sdk.v1.0.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "runtime.LQ.createLiveAppClient = runtime.LQ.createLiveAppClient || createLiveAppClient;" in response.text
    assert "runtime.LQ.liveApp" not in response.text
    assert "query(sql)" in response.text
    assert "mutateInsert(table, data)" in response.text
    assert "mutateUpdateById(table, id, data)" in response.text
    assert "mutateUpdateRows(table, data, where)" in response.text
    assert "mutateDeleteById(table, id)" in response.text
    assert "importCsv(table, file, mode)" in response.text
    assert "/data/query" in response.text
    assert "/data/mutate" in response.text
    assert "/data/import" in response.text


def test_get_live_app_sdk_unknown_version_returns_404(app):
    client = TestClient(app)
    response = client.get("/apps/sdk/lq-sdk.v9.9.js")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_live_app_entry_allows_without_rbac_read_permission(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=2, username="guest", role="guest", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        return {
            "app_id": app_id,
            "entry_file": "entry.html",
            "sdk_version": "1.0",
            "environment": environment,
            "deployed_commit": "abc123",
            "html": "<html><head></head><body>ok</body></html>",
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/entry")
    assert response.status_code == 200


def test_list_live_apps_allows_without_rbac_read_permission(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=2, username="guest", role="guest", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_list_apps(self, user_id, *, has_artifacts_manage=False):
        return []

    monkeypatch.setattr(live_apps.LiveAppService, "list_apps", _fake_list_apps)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps")
    assert response.status_code == 200


def test_get_live_app_not_found_uses_contract_envelope(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_app(self, app_id: int):
        raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

    monkeypatch.setattr(live_apps.LiveAppService, "get_app", _fake_get_app)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/99")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "APP_NOT_FOUND"
    assert payload["details"]["app_id"] == 99


def test_get_live_app_entry_validation_error_uses_contract_envelope(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        raise ValidationError(
            "Live app is currently being updated by another writer.",
            details={"code": "APP_CONFLICT_LOCKED", "app_id": app_id},
        )

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/entry")

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "APP_CONFLICT_LOCKED"
    assert payload["message"] == "Live app is currently being updated by another writer."
    assert payload["details"]["app_id"] == 17
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_get_live_app_entry_not_found_uses_contract_envelope(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/prod/entry")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "APP_NOT_FOUND"
    assert payload["message"] == "Live app not found"
    assert payload["details"]["app_id"] == 17
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_get_live_app_entry_invalid_environment_uses_contract_envelope(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        raise ValidationError(
            "Invalid live app environment.",
            details={"code": "APP_INVALID_ENVIRONMENT", "environment": environment},
        )

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.get("/apps/17/stage/entry")

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "APP_INVALID_ENVIRONMENT"
    assert payload["details"]["environment"] == "stage"
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_query_live_app_data_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert app_id == 17
        assert environment == "dev"
        assert actor_user_id == 1
        assert "app_17.orders" in sql
        return {"rows": [[1, "A"]], "columns": ["id", "name"], "row_count": 1}

    monkeypatch.setattr(live_apps.LiveAppService, "query_data", _fake_query_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post("/apps/v1/17/dev/data/query", json={"sql": "SELECT * FROM app_17.orders"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["row_count"] == 1
    assert payload["data"]["columns"] == ["id", "name"]
    assert payload["meta"]["api_version"] == "v1"


def test_query_live_app_data_namespace_violation_contract_error(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        raise ValidationError(
            "Query references namespace outside the app scope.",
            details={"code": "APP_NAMESPACE_VIOLATION", "app_id": app_id},
        )

    monkeypatch.setattr(live_apps.LiveAppService, "query_data", _fake_query_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post("/apps/v1/17/dev/data/query", json={"sql": "SELECT * FROM public.users"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "APP_NAMESPACE_VIOLATION"
    assert payload["details"]["app_id"] == 17


def test_query_live_app_data_invalid_sql_contract_error(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        raise ValidationError("Invalid SQL", details={"code": "APP_INVALID_SQL", "app_id": app_id})

    monkeypatch.setattr(live_apps.LiveAppService, "query_data", _fake_query_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post("/apps/v1/17/dev/data/query", json={"sql": "DELETE FROM app_17.orders"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "APP_INVALID_SQL"
    assert payload["details"]["app_id"] == 17


def test_mutate_live_app_data_insert_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert app_id == 17
        assert environment == "dev"
        assert operation == "insert"
        assert table == "orders"
        assert actor_user_id == 1
        return {"app_id": app_id, "operation": "insert", "table": "app_17.orders", "affected_rows": 1}

    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data", _fake_mutate_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "insert", "table": "orders", "data": {"id": 1, "name": "a"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["operation"] == "insert"
    assert payload["data"]["affected_rows"] == 1


def test_mutate_live_app_data_update_by_id_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert app_id == 17
        assert operation == "update_by_id"
        assert table == "orders"
        assert data == {"name": "updated"}
        assert row_id == 1
        return {"app_id": app_id, "operation": "update_by_id", "table": "app_17.orders", "affected_rows": 1}

    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data", _fake_mutate_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "update_by_id", "table": "orders", "id": 1, "data": {"name": "updated"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["operation"] == "update_by_id"
    assert payload["data"]["affected_rows"] == 1


def test_mutate_live_app_data_update_rows_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert app_id == 17
        assert operation == "update"
        assert table == "orders"
        assert data == {"status": "shipped"}
        assert where == {"status": "pending"}
        return {"app_id": app_id, "operation": "update", "table": "app_17.orders", "affected_rows": 3}

    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data", _fake_mutate_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "update", "table": "orders", "data": {"status": "shipped"}, "where": {"status": "pending"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["operation"] == "update"
    assert payload["data"]["affected_rows"] == 3


def test_mutate_live_app_data_delete_by_id_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert app_id == 17
        assert operation == "delete_by_id"
        assert table == "orders"
        assert row_id == 1
        return {"app_id": app_id, "operation": "delete_by_id", "table": "app_17.orders", "affected_rows": 1}

    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data", _fake_mutate_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "delete_by_id", "table": "orders", "id": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["operation"] == "delete_by_id"
    assert payload["data"]["affected_rows"] == 1


def test_import_live_app_data_success(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_import_data(
        self,
        app_id: int,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert app_id == 17
        assert environment == "dev"
        assert table == "orders"
        assert mode == "append"
        assert file_name == "import.csv"
        assert file_content.startswith(b"id,name")
        assert actor_user_id == 1
        return {
            "app_id": 17,
            "table": "app_17.orders",
            "file_name": "import.csv",
            "mode": "append",
            "imported_rows": 12,
        }

    monkeypatch.setattr(live_apps.LiveAppService, "import_data", _fake_import_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/import",
        data={"table": "orders", "mode": "append"},
        files={"file": ("import.csv", b"id,name\n1,a\n", "text/csv")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["imported_rows"] == 12


def test_import_live_app_data_forbidden_target_contract_error(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_import_data(
        self,
        app_id: int,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        raise ValidationError(
            "Import targets table outside app namespace.",
            details={"code": "APP_IMPORT_TARGET_FORBIDDEN", "app_id": app_id},
        )

    monkeypatch.setattr(live_apps.LiveAppService, "import_data", _fake_import_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/import",
        data={"table": "public.orders", "mode": "append"},
        files={"file": ("import.csv", b"id,name\n1,a\n", "text/csv")},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "APP_IMPORT_TARGET_FORBIDDEN"
    assert payload["details"]["app_id"] == 17


def test_query_live_app_data_allows_without_rbac_read_permission(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=2, username="guest", role="guest", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    async def _fake_query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        return {"rows": [], "columns": [], "row_count": 0}

    monkeypatch.setattr(live_apps.LiveAppService, "query_data", _fake_query_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post("/apps/v1/17/dev/data/query", json={"sql": "SELECT * FROM app_17.orders"})
    assert response.status_code == 200


def test_mutate_live_app_data_requires_apps_write_permission(app):
    async def _fake_user():
        return UserDTO(id=2, username="guest", role="guest", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "insert", "table": "orders", "data": {"id": 1, "name": "a"}},
    )
    assert response.status_code == 403


def test_import_live_app_data_requires_apps_write_permission(app):
    async def _fake_user():
        return UserDTO(id=2, username="guest", role="guest", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)
    response = client.post(
        "/apps/v1/17/dev/data/import",
        data={"table": "orders", "mode": "append"},
        files={"file": ("import.csv", b"id,name\n1,a\n", "text/csv")},
    )
    assert response.status_code == 403


def test_runtime_data_api_flow_import_query_mutate_query(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    rows: list[dict] = []

    async def _fake_query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert environment == "dev"
        if "count" in sql.lower():
            return {"rows": [[len(rows)]], "columns": ["count"], "row_count": 1}
        return {"rows": [[r["id"], r["name"]] for r in rows], "columns": ["id", "name"], "row_count": len(rows)}

    async def _fake_mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert environment == "dev"
        items = data if isinstance(data, list) else [data]
        rows.extend(items)
        return {
            "app_id": app_id,
            "operation": operation,
            "table": f"app_{app_id}.{table}",
            "affected_rows": len(items),
        }

    async def _fake_import_data(
        self,
        app_id: int,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert environment == "dev"
        lines = file_content.decode("utf-8").strip().splitlines()
        for line in lines[1:]:
            id_str, name = line.split(",", maxsplit=1)
            rows.append({"id": int(id_str), "name": name})
        return {
            "app_id": app_id,
            "table": f"app_{app_id}.{table}",
            "file_name": file_name,
            "mode": mode,
            "imported_rows": max(0, len(lines) - 1),
        }

    monkeypatch.setattr(live_apps.LiveAppService, "query_data", _fake_query_data)
    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data", _fake_mutate_data)
    monkeypatch.setattr(live_apps.LiveAppService, "import_data", _fake_import_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)

    import_resp = client.post(
        "/apps/v1/17/dev/data/import",
        data={"table": "orders", "mode": "append"},
        files={"file": ("import.csv", b"id,name\n1,a\n2,b\n", "text/csv")},
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["data"]["imported_rows"] == 2

    query_resp_1 = client.post("/apps/v1/17/dev/data/query", json={"sql": "SELECT id, name FROM app_17.orders"})
    assert query_resp_1.status_code == 200
    assert query_resp_1.json()["data"]["row_count"] == 2

    mutate_resp = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "insert", "table": "orders", "data": {"id": 3, "name": "c"}},
    )
    assert mutate_resp.status_code == 200
    assert mutate_resp.json()["data"]["affected_rows"] == 1

    query_resp_2 = client.post("/apps/v1/17/dev/data/query", json={"sql": "SELECT count(*) FROM app_17.orders"})
    assert query_resp_2.status_code == 200
    assert query_resp_2.json()["data"]["rows"][0][0] == 3


def test_runtime_smoke_entry_sdk_url_and_data_flow_consistency(app, monkeypatch):
    async def _fake_user():
        return UserDTO(id=1, username="u1", role="admin", tenant_id=9, tenant_name="t9")

    async def _fake_db():
        yield None

    rows: list[dict] = []

    async def _fake_get_entry_page(self, app_id: int, *, environment: str = "prod"):
        return {
            "app_id": app_id,
            "entry_file": "entry.html",
            "sdk_version": "1.0",
            "environment": environment,
            "html": "<html><head></head><body>runtime</body></html>",
        }

    async def _fake_query_data(
        self,
        app_id: int,
        sql: str,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert environment == "dev"
        if "count" in sql.lower():
            return {"rows": [[len(rows)]], "columns": ["count"], "row_count": 1}
        return {"rows": [[r["id"], r["name"]] for r in rows], "columns": ["id", "name"], "row_count": len(rows)}

    async def _fake_mutate_data(
        self,
        app_id: int,
        operation: str,
        table: str,
        data: dict | list[dict] | None = None,
        *,
        where: dict | None = None,
        row_id: int | str | None = None,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert environment == "dev"
        items = data if isinstance(data, list) else [data]
        rows.extend(items)
        return {
            "app_id": app_id,
            "operation": operation,
            "table": f"app_{app_id}.{table}",
            "affected_rows": len(items),
        }

    async def _fake_import_data(
        self,
        app_id: int,
        table: str,
        mode: str,
        file_name: str,
        file_content: bytes,
        *,
        environment: str = "dev",
        actor_user_id: int | None = None,
    ):
        assert environment == "dev"
        lines = file_content.decode("utf-8").strip().splitlines()
        for line in lines[1:]:
            id_str, name = line.split(",", maxsplit=1)
            rows.append({"id": int(id_str), "name": name})
        return {
            "app_id": app_id,
            "table": f"app_{app_id}.{table}",
            "file_name": file_name,
            "mode": mode,
            "imported_rows": max(0, len(lines) - 1),
        }

    monkeypatch.setattr(live_apps.LiveAppService, "get_entry_page", _fake_get_entry_page)
    monkeypatch.setattr(live_apps.LiveAppService, "query_data", _fake_query_data)
    monkeypatch.setattr(live_apps.LiveAppService, "mutate_data", _fake_mutate_data)
    monkeypatch.setattr(live_apps.LiveAppService, "import_data", _fake_import_data)
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db

    client = TestClient(app)

    entry_resp = client.get("/apps/17/dev/entry")
    assert entry_resp.status_code == 200
    assert '<script src="/api/apps/sdk/lq-sdk.v1.0.js"></script>' in entry_resp.text
    assert 'window.LQ.liveApp=window.LQ.createLiveAppClient({appId:17,environment:"dev"});' in entry_resp.text

    sdk_resp = client.get("/apps/sdk/lq-sdk.v1.0.js")
    assert sdk_resp.status_code == 200
    assert "runtime.LQ.createLiveAppClient = runtime.LQ.createLiveAppClient || createLiveAppClient;" in sdk_resp.text

    import_resp = client.post(
        "/apps/v1/17/dev/data/import",
        data={"table": "orders", "mode": "append"},
        files={"file": ("import.csv", b"id,name\n1,a\n2,b\n", "text/csv")},
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["data"]["imported_rows"] == 2

    mutate_resp = client.post(
        "/apps/v1/17/dev/data/mutate",
        json={"operation": "insert", "table": "orders", "data": {"id": 3, "name": "c"}},
    )
    assert mutate_resp.status_code == 200
    assert mutate_resp.json()["data"]["affected_rows"] == 1

    query_resp = client.post("/apps/v1/17/dev/data/query", json={"sql": "SELECT count(*) FROM app_17.orders"})
    assert query_resp.status_code == 200
    assert query_resp.json()["data"]["rows"][0][0] == 3
