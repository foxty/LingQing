"""HTTP-layer coverage for usage time-range query validation."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers.deps.time_range import MAX_USAGE_WINDOW_DAYS
from apps.tenant_app_service.server import app


def _admin_user():
    return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")


async def _fake_db():
    yield object()


@pytest.fixture(autouse=True)
def _grant_tenant_settings(monkeypatch):
    async def _always_allowed(**_kwargs):
        return True

    monkeypatch.setattr("apps.shared.core.auth.role_has_permission", _always_allowed)


@pytest.fixture
def client():
    test_client = TestClient(app)
    app.dependency_overrides[get_current_user] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_token_summary_rejects_partial_explicit_bounds_with_400(client: TestClient):
    """Partial start_time/end_time must be 400, not 500 from non-JSON-serializable error details."""
    resp = client.get(
        "/observability/tenant/token-summary",
        params={"start_time": datetime(2026, 11, 9, 8, tzinfo=UTC).isoformat().replace("+00:00", "Z")},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "together" in body["message"].lower()


def test_token_summary_accepts_last_30_days_explicit_bounds(client: TestClient, monkeypatch):
    """Portal default preset maps to an explicit window within the 90-day cap."""
    end = datetime.now(UTC)
    start = end - timedelta(days=30)

    class _StubService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def get_tenant_usage_stats(self, **kwargs):
            assert abs((kwargs["start_time"] - start).total_seconds()) < 60
            assert abs((kwargs["end_time"] - end).total_seconds()) < 60
            return {
                "tenant_id": 1,
                "period_start": kwargs["start_time"],
                "period_end": kwargs["end_time"],
                "total_llm_calls": 0,
                "total_llm_errors": 0,
                "total_tool_calls": 0,
                "total_tool_errors": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "unique_sessions": 0,
                "unique_threads": 0,
                "unique_users": 0,
            }

    monkeypatch.setattr(
        "apps.tenant_app_service.routers.observability.ObservabilityService.create",
        lambda *_a, **_k: _StubService(),
    )

    resp = client.get(
        "/observability/tenant/token-summary",
        params={
            "start_time": start.isoformat().replace("+00:00", "Z"),
            "end_time": end.isoformat().replace("+00:00", "Z"),
        },
    )
    assert resp.status_code == 200


def test_this_year_explicit_bounds_exceed_usage_cap():
    """Documents why usage UI omits the ``this_year`` preset."""
    from apps.shared.core.exceptions import ValidationError
    from apps.tenant_app_service.routers.deps.time_range import resolve_usage_time_range

    end = datetime.now(UTC)
    start = datetime(end.year, 1, 1, tzinfo=UTC)
    span_days = (end - start).days
    assert span_days > MAX_USAGE_WINDOW_DAYS

    with pytest.raises(ValidationError, match="must not exceed"):
        resolve_usage_time_range(start_time=start, end_time=end, days=None)