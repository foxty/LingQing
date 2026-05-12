"""Unit tests for SSO redirect_uri / callback_url absolute-URL invariant.

Locks that:
- The OIDC redirect_uri sent to the IdP is an absolute URL (not a relative path).
- It is a clean path with NO query params, so it exactly matches what admins
  register at the IdP (Google/Okta/Entra require exact match incl. query string).
- The admin-facing callback_url exactly matches the redirect_uri used at runtime,
  so what an admin registers at the IdP is what the login flow sends.
- The provider is resolved from the `state` on callback, not from the redirect_uri.
"""

from types import SimpleNamespace

import pytest

from apps.tenant_app_service.sso import login_service as login_service_mod
from apps.tenant_app_service.sso import services as services_mod
from apps.tenant_app_service.sso.login_service import SSO_CALLBACK_PATH, SsoLoginService
from apps.tenant_app_service.sso.services import SsoAdminService


@pytest.fixture
def fake_settings(monkeypatch):
    settings = SimpleNamespace(TENANT_APP_API_ORIGIN="https://api.example.com")
    monkeypatch.setattr(services_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(login_service_mod, "get_settings", lambda: settings)
    return settings


def test_admin_callback_url_is_absolute(fake_settings):
    service = SsoAdminService(db=None)
    url = service._callback_url()
    assert url == f"https://api.example.com{SSO_CALLBACK_PATH}"


def test_login_redirect_uri_is_absolute(fake_settings):
    service = SsoLoginService(db=None)
    url = service._redirect_uri()
    assert url == f"https://api.example.com{SSO_CALLBACK_PATH}"


def test_redirect_uri_has_no_query_params(fake_settings):
    """IdPs require exact match incl. query string; keep the URI clean."""
    service = SsoLoginService(db=None)
    url = service._redirect_uri()
    assert "?" not in url
    assert "=" not in url.split("://", 1)[1]


def test_redirect_uri_matches_admin_callback_url(fake_settings):
    """What the admin registers must equal what the login flow sends."""
    admin = SsoAdminService(db=None)
    login = SsoLoginService(db=None)
    assert admin._callback_url() == login._redirect_uri()


def test_redirect_uri_strips_trailing_slash(fake_settings, monkeypatch):
    fake_settings.TENANT_APP_API_ORIGIN = "https://api.example.com/"
    service = SsoLoginService(db=None)
    url = service._redirect_uri()
    assert url == f"https://api.example.com{SSO_CALLBACK_PATH}"
    assert "//auth" not in url
