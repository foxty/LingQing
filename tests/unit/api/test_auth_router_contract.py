"""Auth vs SSO router surface contract tests."""

from starlette.routing import Route

from apps.tenant_app_service.routers import auth as auth_router_module
from apps.tenant_app_service.sso import router as sso_router_module


def _route_paths(router) -> set[str]:
    paths: set[str] = set()
    for route in router.routes:
        if isinstance(route, Route):
            paths.add(route.path)
    return paths


def test_auth_router_exposes_public_login_routes():
    paths = _route_paths(auth_router_module.router)
    assert "/auth/login" in paths
    assert "/auth/resolve-tenant-methods" in paths
    assert "/auth/sso/{provider_id}/start" in paths
    assert "/auth/sso/callback" in paths
    assert "/auth/sso/exchange" in paths
    assert "/auth/invite/accept" in paths
    assert "/auth/password/reset" in paths


def test_sso_router_is_provider_admin_only():
    paths = _route_paths(sso_router_module.router)
    assert paths
    assert all(path.startswith("/tenants/auth-providers") for path in paths)
    assert not any(path.startswith("/auth/") for path in paths)
    assert not any("/tenants/sso/" in path for path in paths)
    assert "/tenants/identity-sources" not in paths
