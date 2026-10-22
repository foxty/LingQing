"""Document collections list router contract."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.document.schemas import DocumentCollectionResponse
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.pagination import PaginationRequest
from apps.tenant_app_service.routers import document_collections


@pytest.fixture
def app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(document_collections.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _fake_db():
        yield object()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    class _FakeService:
        async def list_collections_paginated_for_actor(self, **kwargs):
            _ = kwargs
            pagination = PaginationRequest.with_total(page=1, page_size=20, total=1)
            item = DocumentCollectionResponse(
                id=7,
                tenant_id=1,
                name="Test KB",
                description=None,
                owner_id=1,
                owner_name="admin",
                document_count=0,
                can_write=True,
                can_manage=True,
                has_drive_sync=False,
                sync_folder_name=None,
                sync_status=None,
                last_synced_at=None,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
            return [item], pagination

    def _create_service(db, tenant_id):
        _ = db, tenant_id
        return _FakeService()

    monkeypatch.setattr(document_collections, "_create_service", _create_service)
    return api


def test_list_document_collections_returns_paginated_envelope(app):
    client = TestClient(app)
    response = client.get("/document-collections", params={"page": 1, "page_size": 20, "query": "Test"})
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Test KB"
