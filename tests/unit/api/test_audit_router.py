from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.server import app


def test_export_audit_events_forbidden_without_manage():
    client = TestClient(app)

    async def _read_only():
        return UserDTO(id=2, username="reader", role="member", tenant_id=1, tenant_name="t")

    app.dependency_overrides[get_current_user] = _read_only
    try:
        resp = client.get("/audit/events/export")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def _admin_user():
    return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t")


def test_list_audit_events_rejects_invalid_from_datetime():
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _admin_user
    try:
        resp = client.get("/audit/events", params={"from": "not-a-date"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_export_audit_events_rejects_invalid_from_datetime():
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _admin_user
    try:
        resp = client.get("/audit/events/export", params={"from": "not-a-date"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_list_audit_event_types_returns_catalog():
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _admin_user
    try:
        resp = client.get("/audit/event-types")
        assert resp.status_code == 200
        body = resp.json()
        assert "acl.share.create" in body["items"]
        assert "live_app.data.query" in body["items"]
    finally:
        app.dependency_overrides.clear()