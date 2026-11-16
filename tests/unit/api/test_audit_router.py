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