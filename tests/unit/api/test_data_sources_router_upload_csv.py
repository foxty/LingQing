"""Unit tests for data sources CSV upload router flow."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
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

    async def _fake_db():
        yield object()

    async def _allow_permission(**kwargs):
        return True

    monkeypatch.setattr("apps.shared.core.auth.role_has_permission", _allow_permission)
    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db
    return api


def _asset_response_payload() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": 11,
        "data_source_id": 1,
        "asset_name": "orders",
        "asset_type": "table",
        "columns": [{"name": "id", "type": "int64"}],
        "row_count": 1,
        "source_info": {"created_from": "csv_upload", "file_name": "orders.csv"},
        "meta": {"description": "uploaded from test"},
        "meta_override": None,
        "owner_name": "admin",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "last_metadata_synced_at": None,
        "last_metadata_sync_error": None,
        "last_vector_synced_at": None,
        "last_vector_sync_error": None,
    }


def test_upload_csv_forwards_description_as_keyword_arg(app, monkeypatch):
    captured: dict = {}
    payload = _asset_response_payload()

    class _FakeDBManager:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeDataSourceService:
        async def get_data_source(self, data_source_id: int):
            return SimpleNamespace(id=data_source_id, managed=True)

        async def require_write_access_for_actor(self, *, data_source_id: int, actor):
            return SimpleNamespace(id=data_source_id, managed=True), False

        async def get_db_manager(self, data_source_id: int):
            return _FakeDBManager()

    class _FakeAssetService:
        async def get_asset_by_name_for_actor(self, *, actor, data_source_id: int, asset_name: str):
            return None

        async def import_csv_as_asset_for_actor(
            self,
            *,
            actor,
            data_source_id: int,
            asset_name: str,
            file_name: str,
            csv_path,
            db_manager,
            description: str | None = None,
        ):
            captured["owner_id"] = actor.user_id
            captured["description"] = description
            captured["asset_name"] = asset_name
            captured["file_name"] = file_name
            return object(), 1

    monkeypatch.setattr(
        data_sources,
        "_create_data_source_service",
        lambda db, tenant_id: _FakeDataSourceService(),
    )
    monkeypatch.setattr(
        data_sources,
        "_create_asset_metadata_service",
        lambda db, tenant_id: _FakeAssetService(),
    )
    monkeypatch.setattr(
        "apps.shared.data_source.adapters.domain_asset_metadata_to_api",
        lambda asset: payload,
    )

    client = TestClient(app)
    response = client.post(
        "/data-sources/1/assets/upload-csv",
        data={"asset_name": "orders", "description": "uploaded from test"},
        files={"file": ("orders.csv", b"id,name\n1,a\n", "text/csv")},
    )

    assert response.status_code == 201, response.text
    assert response.json()["asset_name"] == "orders"
    assert captured["owner_id"] == 1
    assert captured["description"] == "uploaded from test"
