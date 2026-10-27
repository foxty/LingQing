"""Unit tests for data source SQL query endpoint asset whitelist."""

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.data_source.service import DataSourceService
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import data_sources


@pytest.fixture
def app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(data_sources.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _allow_permission(**kwargs):
        return True

    monkeypatch.setattr("apps.shared.core.auth.role_has_permission", _allow_permission)
    api.dependency_overrides[get_current_user] = _fake_user
    return api


class _FakeDBManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def query(self, sql: str, params=None):
        return pd.DataFrame([{"id": 1}])


def test_query_data_source_returns_403_for_unregistered_table(app, monkeypatch):
    db_sentinel = object()

    async def _fake_db():
        yield db_sentinel

    app.dependency_overrides[get_db] = _fake_db

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def query_data_for_actor(self, **kwargs):
            from apps.shared.core.exceptions import AuthorizationError

            raise AuthorizationError("Query references unregistered asset 'secret_table'.")

    monkeypatch.setattr(data_sources, "DataSourceService", _FakeService)

    client = TestClient(app)
    response = client.post(
        "/data-sources/4/query",
        json={"sql": "SELECT * FROM secret_table", "limit": 10},
    )

    assert response.status_code == 403
    body = response.json()
    assert "unregistered asset" in body.get("message", "").lower() or "unregistered asset" in str(body).lower()


def test_query_data_source_returns_rows_for_registered_table(app, monkeypatch):
    db_sentinel = object()

    async def _fake_db():
        yield db_sentinel

    app.dependency_overrides[get_db] = _fake_db

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def query_data_for_actor(self, **kwargs):
            return pd.DataFrame([{"id": 1, "name": "A"}])

    monkeypatch.setattr(data_sources, "DataSourceService", _FakeService)

    client = TestClient(app)
    response = client.post(
        "/data-sources/4/query",
        json={"sql": "SELECT * FROM orders", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 1
    assert payload["rows"] == [{"id": 1, "name": "A"}]
