"""Router unit tests for integration pack list/install."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.external_systems.api_connector.schemas import PackSyncSummaryDTO
from apps.shared.external_systems.api_connector.schemas import ApiConnectorResponse
from apps.shared.external_systems.packs.schemas import ApiConnectorPackManifest
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

    now = datetime.now(UTC)
    connector = ApiConnectorResponse(
        id=77,
        tenant_id=1,
        owner_id=1,
        owner_name="admin",
        name="Slack (user)",
        description="Search Slack",
        base_url="https://slack.com/api",
        auth_type="oauth2",
        auth_config={},
        rate_policy={},
        execution_rules={"default_request_encoding": "form"},
        pack_ref="slack-user@1",
        installed_pack_version="1.1.0",
        schema_source_type="manual",
        schema_source_url=None,
        schema_metadata={},
        schema_last_synced_at=None,
        status="active",
        credential_mode="user",
        user_connection_status="not_connected",
        can_write=True,
        pack_update_available=False,
        created_at=now,
        updated_at=now,
    )
    summary = PackSyncSummaryDTO(
        added=1,
        updated=0,
        staled=0,
        unchanged=0,
        installed_pack_version="1.1.0",
        catalog_version="1.1.0",
    )
    install = AsyncMock(return_value=(connector, summary))

    manifest = MagicMock(spec=ApiConnectorPackManifest)
    manifest.pack_id = "slack-user"

    class _FakeCatalog:
        def list(self):
            manifest_row = MagicMock()
            manifest_row.pack_id = "slack-user"
            manifest_row.version = "1.1.0"
            manifest_row.connector.name = "Slack (user)"
            manifest_row.connector.description = "Search Slack"
            return [manifest_row]

        def get(self, pack_id: str):
            assert pack_id == "slack-user"
            return manifest

    class _FakeConnectorService:
        def __init__(self, tenant_id, db_session):
            self.tenant_id = tenant_id

        async def install_integration_pack_for_actor(self, *, actor, manifest, oauth):
            return await install(actor=actor, manifest=manifest, oauth=oauth)

    monkeypatch.setattr(integration_packs, "ApiConnectorPackCatalog", _FakeCatalog)
    monkeypatch.setattr(integration_packs, "ApiConnectorService", _FakeConnectorService)
    return api, install


def test_list_packs_returns_catalog(packs_app):
    api, _install = packs_app
    client = TestClient(api)
    response = client.get("/integration-packs")
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["pack_id"] == "slack-user"
    assert body["items"][0]["version"] == "1.1.0"


def test_install_pack_returns_connector_and_summary(packs_app):
    api, install = packs_app
    client = TestClient(api)
    response = client.post(
        "/integration-packs/install",
        json={
            "pack_id": "slack-user",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "redirect_uri": "https://api.example.test/integrations/oauth/callback",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["connector"]["pack_ref"] == "slack-user@1"
    assert body["connector"]["auth_type"] == "oauth2"
    assert body["connector"]["credential_mode"] == "user"
    assert body["sync_summary"]["added"] == 1
    install.assert_awaited_once()
    oauth = install.await_args.kwargs["oauth"]
    assert oauth.client_id == "synthetic-client"