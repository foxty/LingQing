"""Shared helpers for SSO integration tests."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from tests.integration.conftest import make_auth_headers
from tests.sso.fake_oidc import FakeOidcAdapter


FAKE_OIDC_CONFIG = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "issuer": "https://fake-idp.test",
    "authorize_endpoint": "https://fake-idp.test/authorize",
    "token_endpoint": "https://fake-idp.test/token",
    "userinfo_endpoint": "https://fake-idp.test/userinfo",
    "jwks_uri": "https://fake-idp.test/jwks",
}


async def create_oidc_provider(
    client,
    token: str,
    *,
    enabled: bool = True,
    first_login_policy: str = "jit_create",
    display_name: str | None = None,
) -> dict:
    body = {
        "display_name": display_name or f"Test OIDC {uuid4().hex[:8]}",
        "enabled": enabled,
        "first_login_policy": first_login_policy,
        "config": FAKE_OIDC_CONFIG,
    }
    resp = await client.post(
        "/tenants/auth-providers",
        json=body,
        headers=make_auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def start_sso(client, *, tenant_id: int, provider_id: int) -> tuple[str, str]:
    """Return (state, authorize_url) from SSO start."""
    resp = await client.get(
        f"/auth/sso/{provider_id}/start",
        params={"tenant_id": tenant_id},
    )
    assert resp.status_code == 200, resp.text
    authorize_url = resp.json()["authorize_url"]
    state = parse_qs(urlparse(authorize_url).query)["state"][0]
    return state, authorize_url


async def callback_sso(client, *, state: str, code: str = "fake-code") -> str:
    """Run SSO callback; return redirect Location header."""
    resp = await client.get(
        "/auth/sso/callback",
        params={"state": state, "code": code},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307), resp.text
    return resp.headers["location"]


async def exchange_sso_ticket(client, ticket: str) -> dict:
    resp = await client.post("/auth/sso/exchange", json={"ticket": ticket})
    assert resp.status_code == 200, resp.text
    return resp.json()


def ticket_from_redirect(location: str) -> str:
    return parse_qs(urlparse(location).query)["ticket"][0]


def configure_oidc_identity(
    fake_oidc: FakeOidcAdapter,
    *,
    external_subject: str,
    email: str | None,
    display_name: str | None = None,
) -> None:
    fake_oidc.set_next_identity(
        external_subject=external_subject,
        email=email,
        display_name=display_name,
    )
