"""Rate limits on unauthenticated auth endpoints."""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from apps.shared.core import rate_limit as rl
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.auth.schemas import InviteAcceptResponse
from apps.tenant_app_service.auth.service import AuthService
from apps.tenant_app_service.routers import auth as auth_router_module
from apps.tenant_app_service.sso.dtos import (
    ResolveTenantMethodsResponse,
    SsoCallbackResult,
    SsoExchangeResponse,
    SsoStartResponse,
)
from apps.tenant_app_service.sso.login_service import SsoLoginService
from apps.tenant_app_service.sso.services import SsoAdminService


class _FakeDbSession:
    async def commit(self) -> None:
        return None


async def _empty_db():
    yield _FakeDbSession()


def _patch_limiter(monkeypatch):
    isolated = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    monkeypatch.setattr(rl, "get_rate_limiter", lambda: isolated)
    return isolated


def _tight_dep(policy_name: str):
    return rl.rate_limit_dependency(
        rl.RateLimitPolicy(name=policy_name, max_events=2, window_seconds=60),
    )


def _replace_route_dependency(router: APIRouter, path: str, method: str, dep) -> None:
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            route.dependencies = [Depends(dep)]
            return
    raise AssertionError(f"Route not found: {method} {path}")


def test_sso_exchange_rate_limited(monkeypatch):
    _patch_limiter(monkeypatch)

    async def _fake_exchange(self, ticket: str):
        _ = ticket
        return SsoExchangeResponse(
            access_token="tok",
            token_type="bearer",
            user_id=1,
            username="u",
            role="member",
            tenant_id=1,
            tenant_name="t",
        )

    monkeypatch.setattr(SsoLoginService, "exchange_ticket", _fake_exchange)
    _replace_route_dependency(auth_router_module.router, "/auth/sso/exchange", "POST", _tight_dep("auth.sso.exchange"))

    app = FastAPI()
    app.include_router(auth_router_module.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    body = {"ticket": "abc"}
    assert client.post("/auth/sso/exchange", json=body).status_code == 200
    assert client.post("/auth/sso/exchange", json=body).status_code == 200
    assert client.post("/auth/sso/exchange", json=body).status_code == 429


def test_sso_callback_rate_limited(monkeypatch):
    _patch_limiter(monkeypatch)

    async def _fake_callback(self, *, state: str, code: str, provider_id: int | None = None):
        _ = state, code, provider_id
        return SsoCallbackResult(status="success", ticket="ticket-1")

    monkeypatch.setattr(SsoLoginService, "handle_callback", _fake_callback)
    _replace_route_dependency(
        auth_router_module.router, "/auth/sso/callback", "GET", _tight_dep("auth.sso.callback")
    )

    app = FastAPI()
    app.include_router(auth_router_module.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    url = "/auth/sso/callback?state=s&code=c"
    assert client.get(url, follow_redirects=False).status_code == 307
    assert client.get(url, follow_redirects=False).status_code == 307
    assert client.get(url, follow_redirects=False).status_code == 429


def test_sso_start_rate_limited(monkeypatch):
    _patch_limiter(monkeypatch)

    async def _fake_start(self, tenant_id: int, provider_id: int):
        _ = tenant_id, provider_id
        return SsoStartResponse(authorize_url="https://idp.example/authorize")

    monkeypatch.setattr(SsoLoginService, "start", _fake_start)
    _replace_route_dependency(
        auth_router_module.router, "/auth/sso/{provider_id}/start", "GET", _tight_dep("auth.sso.start")
    )

    app = FastAPI()
    app.include_router(auth_router_module.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    url = "/auth/sso/1/start?tenant_id=1"
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 429


def test_invite_accept_rate_limited(monkeypatch):
    _patch_limiter(monkeypatch)

    async def _fake_accept(self, token: str, password: str):
        _ = token, password
        return InviteAcceptResponse(
            access_token="tok",
            token_type="bearer",
            user=UserDTO(
                id=1,
                username="u",
                role="member",
                tenant_id=1,
                tenant_name="t",
            ),
        )

    monkeypatch.setattr(AuthService, "accept_invite", _fake_accept)
    _replace_route_dependency(auth_router_module.router, "/auth/invite/accept", "POST", _tight_dep("auth.invite.accept"))

    app = FastAPI()
    app.include_router(auth_router_module.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    body = {"token": "t", "password": "p"}
    assert client.post("/auth/invite/accept", json=body).status_code == 200
    assert client.post("/auth/invite/accept", json=body).status_code == 200
    assert client.post("/auth/invite/accept", json=body).status_code == 429


def test_password_reset_rate_limited(monkeypatch):
    _patch_limiter(monkeypatch)

    async def _fake_reset(self, token: str, new_password: str):
        _ = token, new_password

    monkeypatch.setattr(AuthService, "reset_password_with_token", _fake_reset)
    _replace_route_dependency(
        auth_router_module.router, "/auth/password/reset", "POST", _tight_dep("auth.password.reset")
    )

    app = FastAPI()
    app.include_router(auth_router_module.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    body = {"token": "t", "new_password": "new-pass-123"}
    assert client.post("/auth/password/reset", json=body).status_code == 204
    assert client.post("/auth/password/reset", json=body).status_code == 204
    assert client.post("/auth/password/reset", json=body).status_code == 429


def test_resolve_tenant_methods_still_on_auth_router(monkeypatch):
    _patch_limiter(monkeypatch)

    async def _fake_resolve(self, identifier: str):
        _ = identifier
        return ResolveTenantMethodsResponse(
            tenant_id=1,
            tenant_name="t",
            tenant_slug="t",
            login_methods=[],
            force_sso=False,
            emergency_password_available=False,
        )

    monkeypatch.setattr(SsoAdminService, "resolve_tenant_methods", _fake_resolve)
    _replace_route_dependency(
        auth_router_module.router,
        "/auth/resolve-tenant-methods",
        "POST",
        _tight_dep("auth.resolve_tenant_methods"),
    )

    app = FastAPI()
    app.include_router(auth_router_module.router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    body = {"identifier": "u@t"}
    assert client.post("/auth/resolve-tenant-methods", json=body).status_code == 200
    assert client.post("/auth/resolve-tenant-methods", json=body).status_code == 200
    assert client.post("/auth/resolve-tenant-methods", json=body).status_code == 429
