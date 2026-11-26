"""Router unit tests for data-source user OAuth start."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.domain.types import RESOURCE_TYPE_DATA_SOURCE
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import data_sources


@pytest.fixture
def oauth_router_app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(data_sources.router)

    async def _fake_user():
        return UserDTO(id=1, username="member", role="member", tenant_id=1, tenant_name="t1")

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    async def _fake_db():
        yield db

    async def _allow_permission(**kwargs):
        return True

    monkeypatch.setattr("apps.shared.core.auth.role_has_permission", _allow_permission)
    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    class _FakeDataSourceService:
        async def require_read_access_for_actor(self, *, data_source_id: int, actor):
            assert data_source_id == 42
            assert actor.user_id == 1
            return SimpleNamespace(id=data_source_id)

    def _fake_service(_db, _tenant_id):
        return _FakeDataSourceService()

    monkeypatch.setattr(data_sources, "_create_data_source_service", _fake_service)

    class _FakeIntegrationFlow:
        def __init__(self, db_session):
            self.db = db_session

        async def start(self, *, actor, resource_type, resource_id):
            assert resource_type == RESOURCE_TYPE_DATA_SOURCE
            assert resource_id == 42
            return "https://adb.example.test/oidc/v1/authorize?client_id=synthetic"

    monkeypatch.setattr(data_sources, "IntegrationOAuthFlow", _FakeIntegrationFlow)

    return api


def test_data_source_oauth_start_returns_authorization_url(oauth_router_app):
    client = TestClient(oauth_router_app)
    response = client.post("/data-sources/42/oauth/start")
    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://adb.example.test/oidc/v1/authorize")