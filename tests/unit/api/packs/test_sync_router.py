"""Router unit tests for POST /api-connectors/{id}/sync-pack."""

from __future__ import annotations

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
def sync_pack_app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(api_connectors.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _fake_db():
        yield object()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    from datetime import UTC, datetime

    from apps.shared.external_systems.api_connector.schemas import PackSyncSummaryDTO
    from apps.shared.external_systems.api_connector.schemas import ApiConnectorResponse

    now = datetime.now(UTC)
    connector = ApiConnectorResponse(
        id=42,
        tenant_id=1,
        owner_id=1,
        owner_name="admin",
        name="Slack (user)",
        description=None,
        base_url="https://slack.com/api",
        auth_type="oauth2",
        auth_config={},
        rate_policy={},
        execution_rules={},
        pack_ref="slack-user@1",
        installed_pack_version="1.2.0",
        pack_catalog_version="1.2.0",
        pack_update_available=False,
        schema_source_type="manual",
        schema_source_url=None,
        schema_metadata={},
        schema_last_synced_at=None,
        status="active",
        credential_mode="user",
        user_connection_status="not_connected",
        can_write=True,
        created_at=now,
        updated_at=now,
    )
    summary = PackSyncSummaryDTO(
        added=2,
        updated=1,
        staled=0,
        unchanged=9,
        installed_pack_version="1.2.0",
        catalog_version="1.2.0",
    )
    sync_pack = AsyncMock(return_value=(connector, summary))

    class _FakeConnectorService:
        async def sync_installed_pack_for_connector_for_actor(self, *, actor, connector_id, catalog):
            del catalog
            return await sync_pack(actor=actor, connector_id=connector_id)

    async def _fake_service(_db, tenant_id):
        del tenant_id
        return _FakeConnectorService()

    monkeypatch.setattr(api_connectors, "_service", _fake_service)
    return api, sync_pack


def test_sync_pack_route_returns_connector_and_summary(sync_pack_app):
    api, sync_pack = sync_pack_app
    client = TestClient(api)
    response = client.post("/api-connectors/42/sync-pack")
    assert response.status_code == 200
    body = response.json()
    assert body["connector"]["installed_pack_version"] == "1.2.0"
    assert body["summary"]["added"] == 2
    sync_pack.assert_awaited_once()
    assert sync_pack.await_args.kwargs["connector_id"] == 42