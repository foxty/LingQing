"""Auth dependency session lifetime: released vs request-scoped get_db."""

from unittest.mock import AsyncMock

import pytest
from fastapi.dependencies.utils import get_dependant
from starlette.requests import Request

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core import auth as auth_module
from apps.shared.core.auth import get_current_user, require_permission, require_permission_released
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers.chat import chat, chat_stream, get_session_metrics
from apps.tenant_app_service.routers.dashboard import query_dashboard_widget_data


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/query-data", "headers": [], "query_string": b""})


def _user() -> UserDTO:
    return UserDTO(id=7, username="tester", role="admin", tenant_id=1, tenant_name="test_tenant")


def _dependency_calls(func) -> list[object]:
    calls: list[object] = []

    def _walk(dependant) -> None:
        if dependant.call is not None:
            calls.append(dependant.call)
        for child in dependant.dependencies:
            _walk(child)

    _walk(get_dependant(path="/", call=func))
    return calls


class _TrackingSession:
    def __init__(self, events: list[str]):
        self._events = events

    async def __aenter__(self):
        self._events.append("auth_session_enter")
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        self._events.append("auth_session_exit")
        return False


def test_require_permission_holds_request_scoped_get_db():
    checker = require_permission(Permissions.DASHBOARDS_SQL_EXECUTE)
    calls = _dependency_calls(checker)
    assert get_db in calls
    assert get_current_user in calls


def test_require_permission_released_does_not_depend_on_get_db():
    checker = require_permission_released(Permissions.DASHBOARDS_SQL_EXECUTE)
    calls = _dependency_calls(checker)
    assert get_db not in calls
    assert get_current_user not in calls


def test_query_data_route_does_not_depend_on_get_db():
    calls = _dependency_calls(query_dashboard_widget_data)
    assert get_db not in calls
    assert get_current_user not in calls


def test_chat_routes_do_not_depend_on_get_db():
    for route in (chat, chat_stream):
        calls = _dependency_calls(route)
        assert get_db not in calls
        assert get_current_user not in calls


def test_chat_metrics_route_still_uses_request_scoped_get_db():
    calls = _dependency_calls(get_session_metrics)
    assert get_db in calls


@pytest.mark.asyncio
async def test_require_permission_released_closes_session_before_return(monkeypatch):
    events: list[str] = []
    user = _user()

    async def _resolve(request, credentials, db):
        events.append("resolve")
        return user

    async def _ensure(db, current_user, required_permissions):
        events.append("authorize")
        return current_user

    monkeypatch.setattr(auth_module, "app_db_session", lambda: _TrackingSession(events))
    monkeypatch.setattr(auth_module, "_resolve_current_user", _resolve)
    monkeypatch.setattr(auth_module, "_ensure_permission", _ensure)

    checker = require_permission_released(Permissions.DASHBOARDS_SQL_EXECUTE)
    result = await checker(request=_request(), credentials=None)

    assert result == user
    assert events == ["auth_session_enter", "resolve", "authorize", "auth_session_exit"]


@pytest.mark.asyncio
async def test_require_permission_released_closes_session_on_forbidden(monkeypatch):
    from fastapi import HTTPException

    events: list[str] = []

    monkeypatch.setattr(auth_module, "app_db_session", lambda: _TrackingSession(events))
    monkeypatch.setattr(auth_module, "_resolve_current_user", AsyncMock(return_value=_user()))

    async def _deny(db, current_user, required_permissions):
        events.append("deny")
        raise HTTPException(status_code=403, detail="Insufficient permissions.")

    monkeypatch.setattr(auth_module, "_ensure_permission", _deny)

    checker = require_permission_released(Permissions.DASHBOARDS_SQL_EXECUTE)
    with pytest.raises(HTTPException) as exc:
        await checker(request=_request(), credentials=None)

    assert exc.value.status_code == 403
    assert events == ["auth_session_enter", "deny", "auth_session_exit"]
