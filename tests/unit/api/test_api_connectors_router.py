"""Unit tests for api connector router."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.api_connector.schemas import SyncSchemaSummaryDTO
from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.exceptions import ValidationError
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.pagination import PaginationRequest
from apps.tenant_app_service.routers import api_connectors


@pytest.fixture
def app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(api_connectors.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _fake_db():
        yield object()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    class _FakeService:
        def __init__(self):
            self._connector_id = 101
            self._operation_uid = "op-001"

        async def create_connector(self, **kwargs):
            return SimpleNamespace(
                id=self._connector_id,
                tenant_id=1,
                owner_id=1,
                owner_name="admin",
                name=kwargs["name"],
                description=kwargs.get("description"),
                base_url=kwargs["base_url"],
                auth_type=kwargs["auth_type"],
                auth_config=kwargs.get("auth_config") or {},
                rate_policy=kwargs.get("rate_policy"),
                schema_source_type=kwargs["schema_source_type"],
                schema_source_url=kwargs.get("schema_source_url"),
                schema_metadata={},
                schema_last_synced_at=None,
                status="active",
                created_at="2026-04-20T00:00:00Z",
                updated_at="2026-04-20T00:00:00Z",
            )

        async def to_masked_auth_config(self, connector):
            return {}

        async def create_connector(self, **kwargs):
            """Mock create_connector that returns DTO directly."""
            return {
                "id": self._connector_id,
                "tenant_id": 1,
                "owner_id": 1,
                "owner_name": "admin",
                "name": kwargs["name"],
                "description": kwargs.get("description"),
                "base_url": kwargs["base_url"],
                "auth_type": kwargs["auth_type"],
                "auth_config_masked": {},
                "rate_policy": {},
                "schema_source_type": kwargs["schema_source_type"],
                "schema_source_url": kwargs.get("schema_source_url"),
                "schema_metadata": {},
                "schema_last_synced_at": None,
                "status": "active",
                "created_at": "2026-04-20T00:00:00Z",
                "updated_at": "2026-04-20T00:00:00Z",
            }

        async def update_connector_for_actor(self, **kwargs):
            """Mock update that returns DTO directly."""
            connector_id = kwargs["connector_id"]
            return {
                "id": connector_id,
                "tenant_id": 1,
                "owner_id": 1,
                "owner_name": "admin",
                "name": kwargs.get("name") or "orders-api",
                "description": kwargs.get("description"),
                "base_url": kwargs.get("base_url") or "https://8.8.8.8",
                "auth_type": kwargs.get("auth_type") or "none",
                "auth_config_masked": {},
                "rate_policy": {},
                "schema_source_type": kwargs.get("schema_source_type") or "openapi_upload",
                "schema_source_url": kwargs.get("schema_source_url"),
                "schema_metadata": {},
                "schema_last_synced_at": None,
                "status": kwargs.get("status") or "active",
                "created_at": "2026-04-20T00:00:00Z",
                "updated_at": "2026-04-20T00:00:00Z",
            }

        async def list_connectors_for_actor(self, **kwargs):
            """Mock list connectors that returns DTOs directly."""
            return []

        async def get_connector_for_actor(self, **kwargs):
            """Mock get connector that returns DTO directly."""
            connector_id = kwargs["connector_id"]
            return {
                "id": connector_id,
                "tenant_id": 1,
                "owner_id": 1,
                "owner_name": "admin",
                "name": "orders-api",
                "description": "orders",
                "base_url": "https://8.8.8.8",
                "auth_type": "none",
                "auth_config_masked": {},
                "rate_policy": {},
                "schema_source_type": "openapi_upload",
                "schema_source_url": None,
                "schema_metadata": {},
                "schema_last_synced_at": None,
                "status": "active",
                "created_at": "2026-04-20T00:00:00Z",
                "updated_at": "2026-04-20T00:00:00Z",
            }

        async def delete_connector_for_actor(self, **kwargs):
            return None

        async def sync_operations_from_schema_for_actor(self, **kwargs):
            marker = kwargs.get("file_content") or ""
            if "updated-and-staled" in marker:
                return SyncSchemaSummaryDTO(added=1, updated=2, staled=1, unchanged=3)
            return SyncSchemaSummaryDTO(added=1, updated=0, staled=0, unchanged=0)

        async def list_operations_for_actor(self, **kwargs):
            rows = [
                SimpleNamespace(
                    id=1,
                    connector_id=101,
                    operation_uid=self._operation_uid,
                    method="GET",
                    path_template="/orders/{id}",
                    operation_id="getOrder",
                    summary="get order",
                    description=None,
                    tags=["orders"],
                    request_schema=None,
                    response_schema=None,
                    auth_requirement="none",
                    risk_level="low",
                    source="imported",
                    upstream_key="uk-001",
                    content_hash="ch-001",
                    indexed_content_hash=None,
                    status="active",
                    last_vector_synced_at=None,
                    last_vector_sync_error=None,
                    last_vector_sync_failed_at=None,
                    owner_id=1,
                    created_at="2026-04-20T00:00:00Z",
                    updated_at="2026-04-20T00:00:00Z",
                )
            ]
            return rows, PaginationRequest(page=kwargs["page"], page_size=kwargs["page_size"], total=len(rows))

        async def add_manual_operation_for_actor(self, **kwargs):
            return SimpleNamespace(
                id=2,
                connector_id=kwargs["connector_id"],
                operation_uid="op-manual-001",
                method=kwargs["method"],
                path_template=kwargs["path_template"],
                operation_id=kwargs.get("operation_id"),
                summary=kwargs["summary"],
                description=kwargs.get("description"),
                tags=kwargs.get("tags") or [],
                request_schema=kwargs.get("request_schema"),
                response_schema=kwargs.get("response_schema"),
                auth_requirement=kwargs.get("auth_requirement", "none"),
                risk_level=kwargs.get("risk_level", "low"),
                source="manual",
                upstream_key=None,
                content_hash=None,
                indexed_content_hash=None,
                status="active",
                last_vector_synced_at=None,
                last_vector_sync_error=None,
                last_vector_sync_failed_at=None,
                owner_id=1,
                created_at="2026-04-20T00:00:00Z",
                updated_at="2026-04-20T00:00:00Z",
            )

        async def search_operations_for_actor(self, **kwargs):
            rows = [
                SimpleNamespace(
                    id=2,
                    connector_id=101,
                    operation_uid="op-manual-001",
                    method="GET",
                    path_template="/customers",
                    operation_id="listCustomers",
                    summary="list customers",
                    description="query customer list",
                    tags=["crm"],
                    request_schema=None,
                    response_schema=None,
                    auth_requirement="none",
                    risk_level="low",
                    source="manual",
                    upstream_key=None,
                    content_hash=None,
                    indexed_content_hash=None,
                    status="active",
                    last_vector_synced_at=None,
                    last_vector_sync_error=None,
                    last_vector_sync_failed_at=None,
                    owner_id=1,
                    created_at="2026-04-20T00:00:00Z",
                    updated_at="2026-04-20T00:00:00Z",
                )
            ]
            return rows, PaginationRequest(page=kwargs["page"], page_size=kwargs["page_size"], total=len(rows))

        async def update_operation_for_actor(self, **kwargs):
            operation_id = kwargs["operation_id"]
            if operation_id == 1:
                raise ValidationError("Imported operation cannot be edited")
            return SimpleNamespace(
                id=operation_id,
                connector_id=101,
                operation_uid="op-manual-001",
                method=kwargs.get("method") or "GET",
                path_template=kwargs.get("path_template") or "/customers",
                operation_id=kwargs.get("operation_id_new") or "listCustomers",
                summary=kwargs.get("summary") or "list customers",
                description=kwargs.get("description") or "query customer list",
                tags=kwargs.get("tags") or ["crm"],
                request_schema=kwargs.get("request_schema"),
                response_schema=kwargs.get("response_schema"),
                auth_requirement=kwargs.get("auth_requirement") or "none",
                risk_level=kwargs.get("risk_level") or "low",
                source="manual",
                upstream_key=None,
                content_hash=None,
                indexed_content_hash=None,
                status="active",
                last_vector_synced_at=None,
                last_vector_sync_error=None,
                last_vector_sync_failed_at=None,
                owner_id=1,
                created_at="2026-04-20T00:00:00Z",
                updated_at="2026-04-20T00:00:00Z",
            )

        async def delete_operation_for_actor(self, **kwargs):
            operation_id = kwargs["operation_id"]
            if operation_id == 1:
                raise ValidationError("Imported operation cannot be deleted")
            return None

    class _FakeExecutionService:
        def __init__(self, tenant_id, db_session):
            pass

        async def execute_operation_for_actor(self, **kwargs):
            return SimpleNamespace(status_code=200, body={"ok": True}, headers={}, elapsed_ms=12.0, error=None)

    service = _FakeService()

    async def _fake_service(db, tenant_id):
        return service

    monkeypatch.setattr(api_connectors, "_service", _fake_service)
    monkeypatch.setattr(api_connectors, "ApiConnectorExecutionService", _FakeExecutionService)

    return api


def test_connector_crud_sync_and_call_flow(app):
    client = TestClient(app)

    create_resp = client.post(
        "/api-connectors",
        json={
            "name": "orders-api",
            "description": "orders",
            "base_url": "https://8.8.8.8",
            "auth_type": "none",
            "auth_config": {},
            "rate_policy": {},
            "schema_source_type": "openapi_upload",
            "schema_source_url": None,
        },
    )
    assert create_resp.status_code == 201
    connector = create_resp.json()
    connector_id = connector["id"]

    sync_resp = client.post(
        f"/api-connectors/{connector_id}/sync-schema",
        json={
            "file_content": """
openapi: 3.0.0
info: {title: Demo, version: 1.0.0}
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string}
      responses:
        '200': {description: ok}
""".strip(),
        },
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["operations_created"] == 1
    assert sync_resp.json()["added"] == 1

    list_resp = client.get(f"/api-connectors/{connector_id}/operations")
    assert list_resp.status_code == 200
    operations = list_resp.json()["items"]
    assert len(operations) == 1

    operation_uid = operations[0]["operation_uid"]
    call_resp = client.post(
        f"/api-connectors/operations/{operation_uid}/call",
        json={"parameters": {"path": {"id": "101"}}},
    )
    assert call_resp.status_code == 200
    assert call_resp.json()["status_code"] == 200
    assert call_resp.json()["body"]["ok"] is True


def test_search_operations_endpoint(app):
    client = TestClient(app)

    create_resp = client.post(
        "/api-connectors",
        json={
            "name": "manual-api",
            "description": "manual",
            "base_url": "https://8.8.8.8",
            "auth_type": "none",
            "auth_config": {},
            "rate_policy": {},
            "schema_source_type": "manual",
            "schema_source_url": None,
        },
    )
    connector_id = create_resp.json()["id"]

    add_resp = client.post(
        f"/api-connectors/{connector_id}/operations",
        json={
            "method": "GET",
            "path_template": "/customers",
            "operation_id": "listCustomers",
            "summary": "list customers",
            "description": "query customer list",
            "tags": ["crm"],
            "request_schema": {"type": "object", "properties": {}},
            "response_schema": {"status": "200", "schema": {"type": "object"}},
            "auth_requirement": "none",
            "risk_level": "low",
        },
    )
    assert add_resp.status_code == 201

    search_resp = client.get("/api-connectors/operations/search", params={"q": "customers"})
    assert search_resp.status_code == 200
    payload = search_resp.json()
    assert payload["total"] >= 1


def test_sync_schema_response_includes_full_diff_summary(app):
    client = TestClient(app)

    create_resp = client.post(
        "/api-connectors",
        json={
            "name": "orders-api",
            "description": "orders",
            "base_url": "https://8.8.8.8",
            "auth_type": "none",
            "auth_config": {},
            "rate_policy": {},
            "schema_source_type": "openapi_upload",
            "schema_source_url": None,
        },
    )
    connector_id = create_resp.json()["id"]

    sync_resp = client.post(
        f"/api-connectors/{connector_id}/sync-schema",
        json={"file_content": "updated-and-staled"},
    )

    assert sync_resp.status_code == 200
    payload = sync_resp.json()
    assert payload["operations_created"] == 1
    assert payload["added"] == 1
    assert payload["updated"] == 2
    assert payload["staled"] == 1
    assert payload["unchanged"] == 3


def test_imported_operation_update_and_delete_are_rejected(app):
    client = TestClient(app)

    update_resp = client.patch(
        "/api-connectors/operations/1",
        json={"summary": "new summary"},
    )
    assert update_resp.status_code == 400
    assert update_resp.json()["code"] == "VALIDATION_ERROR"
    assert "Imported operation cannot be edited" in update_resp.json()["message"]

    delete_resp = client.delete("/api-connectors/operations/1")
    assert delete_resp.status_code == 400
    assert delete_resp.json()["code"] == "VALIDATION_ERROR"
    assert "Imported operation cannot be deleted" in delete_resp.json()["message"]


def test_manual_operation_update_and_delete_success(app):
    client = TestClient(app)

    update_resp = client.patch(
        "/api-connectors/operations/2",
        json={
            "method": "POST",
            "path_template": "/customers/{id}",
            "operation_id": "updateCustomer",
            "summary": "update customer",
        },
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()
    assert payload["id"] == 2
    assert payload["method"] == "POST"
    assert payload["path_template"] == "/customers/{id}"
    assert payload["operation_id"] == "updateCustomer"
    assert payload["summary"] == "update customer"

    delete_resp = client.delete("/api-connectors/operations/2")
    assert delete_resp.status_code == 204


def test_connector_update_and_delete_success(app):
    client = TestClient(app)

    update_resp = client.patch(
        "/api-connectors/101",
        json={
            "name": "orders-api-v2",
            "base_url": "https://1.1.1.1",
            "description": "updated",
        },
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()
    assert payload["id"] == 101
    assert payload["name"] == "orders-api-v2"
    assert payload["base_url"] == "https://1.1.1.1"
    assert payload["description"] == "updated"

    delete_resp = client.delete("/api-connectors/101")
    assert delete_resp.status_code == 204


def test_manual_operation_update_and_delete_succeed(app):
    client = TestClient(app)

    update_resp = client.patch(
        "/api-connectors/operations/2",
        json={"summary": "updated summary", "tags": ["crm", "vip"]},
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["source"] == "manual"
    assert body["summary"] == "updated summary"
    assert body["tags"] == ["crm", "vip"]

    delete_resp = client.delete("/api-connectors/operations/2")
    assert delete_resp.status_code == 204
