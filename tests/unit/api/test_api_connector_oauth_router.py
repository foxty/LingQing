"""Router unit tests for API connector OAuth start + shared callback."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import api_connectors


@pytest.fixture
def oauth_router_app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(api_connectors.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    async def _fake_db():
        yield db

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    class _FakeService:
        async def get_connector_for_actor(self, **kwargs):
            return {"id": kwargs["connector_id"], "auth_type": "oauth2"}

    async def _fake_service(db_session, tenant_id):
        return _FakeService()

    monkeypatch.setattr(api_connectors, "_service", _fake_service)

    class _FakeFlow:
        def __init__(self, db_session):
            self.db = db_session

        async def start(self, *, actor, connector_id):
            assert actor.user_id == 1
            assert connector_id == 42
            return "https://auth.example.test/authorize?state=synthetic&client_id=c"

        async def complete_from_callback(self, *, code, state):
            assert code == "auth-code"
            assert state == "encrypted-state"
            return 42

        @staticmethod
        def portal_success_url(connector_id: int) -> str:
            return f"https://portal.example.test/api-connectors/{connector_id}?oauth=connected"

        @staticmethod
        def portal_error_url(*, connector_id: int | None = None) -> str:
            if connector_id is not None:
                return f"https://portal.example.test/api-connectors/{connector_id}?oauth=error"
            return "https://portal.example.test/api-connectors?oauth=error"

    monkeypatch.setattr(api_connectors, "ApiConnectorOAuthFlow", _FakeFlow)
    monkeypatch.setattr(
        api_connectors.OAuthStateCodec,
        "decode",
        lambda self, state: SimpleNamespace(connector_id=42),
    )

    return api, db


def test_oauth_start_returns_authorization_url(oauth_router_app):
    api, _db = oauth_router_app
    client = TestClient(api)
    response = client.post("/api-connectors/42/oauth/start")
    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://auth.example.test/authorize")


def test_oauth_callback_success_redirects_and_commits(oauth_router_app):
    api, db = oauth_router_app
    client = TestClient(api, follow_redirects=False)
    response = client.get(
        "/api-connectors/oauth/callback",
        params={"code": "auth-code", "state": "encrypted-state"},
    )
    assert response.status_code in (302, 307)
    assert response.headers["location"] == ("https://portal.example.test/api-connectors/42?oauth=connected")
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


def test_oauth_callback_provider_error_redirects_without_complete(oauth_router_app, monkeypatch):
    api, db = oauth_router_app

    class _BoomFlow:
        def __init__(self, db_session):
            raise AssertionError("complete should not run on provider error")

        @staticmethod
        def portal_error_url(*, connector_id: int | None = None) -> str:
            return f"https://portal.example.test/api-connectors/{connector_id}?oauth=error"

    monkeypatch.setattr(api_connectors, "ApiConnectorOAuthFlow", _BoomFlow)
    client = TestClient(api, follow_redirects=False)
    response = client.get(
        "/api-connectors/oauth/callback",
        params={"error": "access_denied", "state": "encrypted-state"},
    )
    assert response.status_code in (302, 307)
    assert "oauth=error" in response.headers["location"]
    db.commit.assert_not_awaited()


def test_oauth_callback_validation_error_rolls_back(oauth_router_app, monkeypatch):
    api, db = oauth_router_app
    from apps.shared.core.exceptions import ValidationError

    class _FailFlow:
        def __init__(self, db_session):
            pass

        async def complete_from_callback(self, *, code, state):
            raise ValidationError("bad state")

        @staticmethod
        def portal_error_url(*, connector_id: int | None = None) -> str:
            return f"https://portal.example.test/api-connectors/{connector_id}?oauth=error"

    monkeypatch.setattr(api_connectors, "ApiConnectorOAuthFlow", _FailFlow)
    client = TestClient(api, follow_redirects=False)
    response = client.get(
        "/api-connectors/oauth/callback",
        params={"code": "auth-code", "state": "encrypted-state"},
    )
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("?oauth=error")
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
