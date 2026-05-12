"""Unit tests for context resources search router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.context_resource.domain import ContextResourceItem
from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import context_resources


@pytest.fixture
def app():
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(context_resources.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _fake_db():
        yield object()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db
    return api


@pytest.fixture
def client(app):
    return TestClient(app)


class _FakeSearchService:
    def __init__(self, items: list[ContextResourceItem] | None = None) -> None:
        self.items = items or []
        self.last_query: str | None = None
        self.last_limit: int | None = None

    async def search(self, query: str, limit: int = 10) -> list[ContextResourceItem]:
        self.last_query = query
        self.last_limit = limit
        return self.items


@pytest.fixture
def fake_service(monkeypatch):
    service = _FakeSearchService()

    def _fake_create_service(_db, tenant_id: int):
        assert tenant_id == 1
        return service

    monkeypatch.setattr(context_resources, "_create_service", _fake_create_service)
    return service


class TestSearchContextResources:
    def test_empty_query_returns_200(self, client, fake_service):
        fake_service.items = [
            ContextResourceItem(resource_type="document", resource_id=1, title="readme.pdf"),
        ]

        resp = client.get("/context-resources/search", params={"query": "", "limit": 8})

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == [
            {
                "resource_type": "document",
                "resource_id": 1,
                "title": "readme.pdf",
                "subtitle": None,
            }
        ]
        assert fake_service.last_query == ""
        assert fake_service.last_limit == 8

    def test_missing_query_defaults_to_empty(self, client, fake_service):
        resp = client.get("/context-resources/search", params={"limit": 8})

        assert resp.status_code == 200
        assert resp.json() == {"items": []}
        assert fake_service.last_query == ""

    def test_whitespace_query_is_trimmed(self, client, fake_service):
        resp = client.get("/context-resources/search", params={"query": "   ", "limit": 8})

        assert resp.status_code == 200
        assert fake_service.last_query == ""

    def test_keyword_query_returns_matches(self, client, fake_service):
        fake_service.items = [
            ContextResourceItem(
                resource_type="dashboard",
                resource_id=42,
                title="Sales Overview",
            ),
        ]

        resp = client.get("/context-resources/search", params={"query": "sales", "limit": 10})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Sales Overview"
        assert fake_service.last_query == "sales"

    def test_query_over_max_length_returns_422(self, client, fake_service):
        resp = client.get("/context-resources/search", params={"query": "x" * 201})
        assert resp.status_code == 422
