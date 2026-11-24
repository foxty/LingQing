"""Router unit tests for integration pack list/install."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.external_systems.packs.schemas import ApiConnectorPackSummary
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import integration_packs


@pytest.fixture
def packs_app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(integration_packs.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _fake_db():
        yield object()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    install = AsyncMock(
        return_value={
            "id": 77,
            "tenant_id": 1,
            "owner_id": 1,
            "owner_name": "admin",
            "name": "Slack (user)",
            "description": "Search Slack",
            "base_url": "https://slack.com/api",
            "auth_type": "oauth2",
            "auth_config": {},
            "rate_policy": {},
            "execution_rules": {"default_request_encoding": "form"},
            "pack_ref": "slack-user@1",
            "schema_source_type": "manual",
            "schema_source_url": None,
            "schema_metadata": {},
            "schema_last_synced_at": None,
            "status": "active",
            "credential_mode": "user",
            "user_connection_status": "not_connected",
            "created_at": "2026-04-20T00:00:00Z",
            "updated_at": "2026-04-20T00:00:00Z",
        }
    )

    class _FakePackService:
        def __init__(self, tenant_id, db):
            self.tenant_id = tenant_id

        def list_packs(self):
            return [
                ApiConnectorPackSummary(
                    pack_id="slack-user",
                    version="1.1.0",
                    name="Slack (user)",
                    description="Search Slack",
                )
            ]

        async def install(self, *, actor, request):
            return await install(actor=actor, request=request)

    monkeypatch.setattr(integration_packs, "ApiConnectorPackService", _FakePackService)
    return api, install


def test_list_packs_returns_catalog(packs_app):
    api, _install = packs_app
    client = TestClient(api)
    response = client.get("/integration-packs")
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["pack_id"] == "slack-user"
    assert body["items"][0]["version"] == "1.1.0"


def test_install_pack_returns_connector(packs_app):
    api, install = packs_app
    client = TestClient(api)
    response = client.post(
        "/integration-packs/install",
        json={
            "pack_id": "slack-user",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "redirect_uri": "https://api.example.test/api-connectors/oauth/callback",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["pack_ref"] == "slack-user@1"
    assert body["auth_type"] == "oauth2"
    assert body["credential_mode"] == "user"
    install.assert_awaited_once()
    request = install.await_args.kwargs["request"]
    assert request.pack_id == "slack-user"
    assert request.client_id == "synthetic-client"
