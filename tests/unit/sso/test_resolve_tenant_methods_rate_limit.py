"""Rate limit on public resolve-tenant-methods endpoint."""

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core import rate_limit as rl
from apps.shared.db.session import get_db
from apps.tenant_app_service.sso.dtos import ResolveTenantMethodsRequest, ResolveTenantMethodsResponse
from apps.tenant_app_service.sso.services import SsoAdminService


async def _empty_db():
    yield object()


def test_resolve_tenant_methods_rate_limited_by_ip(monkeypatch):
    async def _fake_resolve(self, identifier: str):
        _ = identifier
        return ResolveTenantMethodsResponse(
            tenant_id=1,
            tenant_name="t1",
            tenant_slug="t1",
            login_methods=[],
            force_sso=False,
            emergency_password_available=False,
        )

    isolated = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    monkeypatch.setattr(rl, "get_rate_limiter", lambda: isolated)
    monkeypatch.setattr(SsoAdminService, "resolve_tenant_methods", _fake_resolve)

    dep = rl.rate_limiter("auth.resolve_tenant_methods", 2, 60)
    router = APIRouter()

    @router.post(
        "/auth/resolve-tenant-methods",
        response_model=ResolveTenantMethodsResponse,
        dependencies=[Depends(dep)],
    )
    async def endpoint(
        request: ResolveTenantMethodsRequest,
        db: AsyncSession = Depends(get_db),
    ):
        service = SsoAdminService(db)
        return await service.resolve_tenant_methods(request.identifier)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _empty_db

    client = TestClient(app, raise_server_exceptions=False)
    body = {"identifier": "user@tenant"}
    assert client.post("/auth/resolve-tenant-methods", json=body).status_code == 200
    assert client.post("/auth/resolve-tenant-methods", json=body).status_code == 200
    assert client.post("/auth/resolve-tenant-methods", json=body).status_code == 429
