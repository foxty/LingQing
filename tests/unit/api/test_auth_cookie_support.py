"""Unit tests for hybrid auth support (header + cookie)."""

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.auth.schemas import LoginResponse
from apps.tenant_app_service.routers import auth as auth_router


class _FakeMembershipResult:
    def scalar_one_or_none(self):
        return SimpleNamespace(status="active")


class _FakeDb:
    async def execute(self, _stmt):
        return _FakeMembershipResult()


async def _fake_db():
    yield _FakeDb()


def _fake_user():
    return SimpleNamespace(tenant_id=9, preferences={"timezone_iana": "UTC"}, status="active")


def _fake_token_payload():
    return {
        "user_id": 7,
        "sub": "u1",
        "role": "admin",
        "tenant_id": 9,
        "tenant_name": "t9",
    }


def test_get_current_user_supports_cookie_fallback_for_preview_routes(monkeypatch):
    async def _fake_get_by_id(self, user_id: int):
        assert user_id == 7
        return _fake_user()

    monkeypatch.setattr("apps.shared.core.auth.jwt.decode", lambda *args, **kwargs: _fake_token_payload())
    monkeypatch.setattr("apps.shared.core.auth.BaseRepository.get_by_id", _fake_get_by_id)

    app = FastAPI()
    app.dependency_overrides[get_db] = _fake_db

    @app.get("/apps/7/dev/entry")
    async def me(current_user: UserDTO = Depends(get_current_user)):
        return {"id": current_user.id, "tenant_id": current_user.tenant_id}

    client = TestClient(app)
    client.cookies.set("access_token", "cookie-jwt-token")
    response = client.get("/apps/7/dev/entry")
    assert response.status_code == 200
    assert response.json() == {"id": 7, "tenant_id": 9}


def test_get_current_user_supports_cookie_fallback_for_app_asset_routes(monkeypatch):
    async def _fake_get_by_id(self, user_id: int):
        assert user_id == 7
        return _fake_user()

    monkeypatch.setattr("apps.shared.core.auth.jwt.decode", lambda *args, **kwargs: _fake_token_payload())
    monkeypatch.setattr("apps.shared.core.auth.BaseRepository.get_by_id", _fake_get_by_id)

    app = FastAPI()
    app.dependency_overrides[get_db] = _fake_db

    @app.get("/apps/7/dev/styles/main.css")
    async def asset(current_user: UserDTO = Depends(get_current_user)):
        return {"id": current_user.id, "tenant_id": current_user.tenant_id}

    client = TestClient(app)
    client.cookies.set("access_token", "cookie-jwt-token")
    response = client.get("/apps/7/dev/styles/main.css")
    assert response.status_code == 200
    assert response.json() == {"id": 7, "tenant_id": 9}


def test_get_current_user_rejects_deactivated_membership(monkeypatch):
    class _InactiveMembershipResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(status="inactive")

    class _InactiveDb:
        async def execute(self, _stmt):
            return _InactiveMembershipResult()

    async def _inactive_db():
        yield _InactiveDb()

    async def _fake_get_by_id(self, user_id: int):
        assert user_id == 7
        return _fake_user()

    monkeypatch.setattr("apps.shared.core.auth.jwt.decode", lambda *args, **kwargs: _fake_token_payload())
    monkeypatch.setattr("apps.shared.core.auth.BaseRepository.get_by_id", _fake_get_by_id)

    app = FastAPI()
    app.dependency_overrides[get_db] = _inactive_db

    @app.get("/apps/7/dev/entry")
    async def me(current_user: UserDTO = Depends(get_current_user)):
        return {"id": current_user.id}

    client = TestClient(app)
    client.cookies.set("access_token", "cookie-jwt-token")
    response = client.get("/apps/7/dev/entry")
    assert response.status_code == 401


def test_get_current_user_rejects_cookie_fallback_on_non_preview_routes(monkeypatch):
    async def _empty_db():
        yield object()

    monkeypatch.setattr("apps.shared.core.auth.jwt.decode", lambda *args, **kwargs: _fake_token_payload())

    app = FastAPI()
    app.dependency_overrides[get_db] = _empty_db

    @app.get("/me")
    async def me(current_user: UserDTO = Depends(get_current_user)):
        return {"id": current_user.id}

    client = TestClient(app)
    client.cookies.set("access_token", "cookie-jwt-token")
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_login_sets_access_token_cookie(monkeypatch):
    async def _empty_db():
        yield object()

    async def _fake_authenticate(self, credentials):
        _ = credentials
        return LoginResponse(
            access_token="jwt-token-abc",
            token_type="bearer",
            user=UserDTO(id=11, username="u1", role="admin", tenant_id=9, tenant_name="t9"),
        )

    monkeypatch.setattr("apps.tenant_app_service.auth.service.AuthService.authenticate", _fake_authenticate)

    app = FastAPI()
    app.include_router(auth_router.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app)
    response = client.post("/auth/login", json={"username": "u1@t9", "password": "pwd"})
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=jwt-token-abc" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
