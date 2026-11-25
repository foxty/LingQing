"""Unit tests for OAuth2TokenClient token exchange / refresh."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.infra.oauth import (
    OAuthTokenClientConfig,
    build_authorize_url,
)
from apps.shared.infra.oauth.client import OAuth2TokenClient
from apps.shared.infra.oauth.constants import (
    TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC,
    TOKEN_AUTH_METHOD_CLIENT_SECRET_POST,
)


@dataclass
class _Config:
    token_url: str = "https://auth.example.test/token"
    client_id: str = "synthetic-client"
    client_secret: str | None = "synthetic-secret"
    token_auth_method: str = TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
    token_response_path: str | None = None


class _FakeResponse:
    def __init__(self, *, status: int, payload: dict):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    last_post: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    def post(self, url, data=None, auth=None):
        type(self).last_post = {"url": url, "data": dict(data or {}), "auth": auth}
        return _FakeResponse(status=self._status, payload=self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _patch_session(monkeypatch, *, status: int, payload: dict):
    session_cls = type(
        "_Session",
        (_FakeSession,),
        {"_status": status, "_payload": payload, "last_post": None},
    )
    monkeypatch.setattr("apps.shared.infra.oauth.client.aiohttp.ClientSession", session_cls)
    return session_cls


@pytest.mark.asyncio
async def test_exchange_code_reads_nested_slack_authed_user_path(monkeypatch):
    session_cls = _patch_session(
        monkeypatch,
        status=200,
        payload={
            "ok": True,
            "authed_user": {
                "access_token": "xoxp-user-token",
                "refresh_token": "xoxe-refresh",
                "token_type": "user",
                "expires_in": 3600,
                "scope": "search:read",
            },
        },
    )
    client = OAuth2TokenClient()
    tokens = await client.exchange_code(
        config=_Config(token_response_path="authed_user"),
        code="auth-code",
        code_verifier="verifier",
        redirect_uri="https://api.example.test/integrations/oauth/callback",
    )

    assert tokens.access_token == "xoxp-user-token"
    assert tokens.refresh_token == "xoxe-refresh"
    assert tokens.token_type == "Bearer"
    assert tokens.scopes == "search:read"
    assert tokens.expires_at is not None
    assert session_cls.last_post is not None
    assert session_cls.last_post["data"]["grant_type"] == "authorization_code"
    assert session_cls.last_post["data"]["client_secret"] == "synthetic-secret"
    assert session_cls.last_post["auth"] is None


@pytest.mark.asyncio
async def test_refresh_uses_client_secret_basic_auth(monkeypatch):
    session_cls = _patch_session(
        monkeypatch,
        status=200,
        payload={"access_token": "new-access", "token_type": "Bearer", "expires_in": 120},
    )
    client = OAuth2TokenClient()
    tokens = await client.refresh(
        config=_Config(token_auth_method=TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC),
        refresh_token="refresh-token",
    )

    assert tokens.access_token == "new-access"
    assert session_cls.last_post is not None
    assert "client_secret" not in session_cls.last_post["data"]
    assert session_cls.last_post["auth"] is not None
    assert session_cls.last_post["auth"].login == "synthetic-client"
    assert session_cls.last_post["auth"].password == "synthetic-secret"


@pytest.mark.asyncio
async def test_exchange_raises_on_provider_error_payload(monkeypatch):
    _patch_session(
        monkeypatch,
        status=200,
        payload={"error": "invalid_grant", "error_description": "bad code"},
    )
    client = OAuth2TokenClient()
    with pytest.raises(ValidationError, match="invalid_grant"):
        await client.exchange_code(
            config=_Config(),
            code="bad",
            code_verifier="verifier",
            redirect_uri="https://api.example.test/callback",
        )


@pytest.mark.asyncio
async def test_exchange_raises_on_http_error_status(monkeypatch):
    _patch_session(monkeypatch, status=500, payload={"error": "server_error"})
    client = OAuth2TokenClient()
    with pytest.raises(ValidationError, match="HTTP 500"):
        await client.exchange_code(
            config=_Config(),
            code="auth-code",
            code_verifier="verifier",
            redirect_uri="https://api.example.test/callback",
        )


@pytest.mark.asyncio
async def test_exchange_maps_transport_error_to_validation_error(monkeypatch):
    class _FailingSession(_FakeSession):
        def post(self, url, data=None, auth=None):
            raise aiohttp.ClientConnectionError("synthetic connection failure")

    monkeypatch.setattr("apps.shared.infra.oauth.client.aiohttp.ClientSession", _FailingSession)

    with pytest.raises(ValidationError, match="request failed"):
        await OAuth2TokenClient().exchange_code(
            config=_Config(),
            code="auth-code",
            code_verifier="verifier",
            redirect_uri="https://api.example.test/callback",
        )


def test_nested_payload_returns_empty_for_missing_path():
    assert OAuth2TokenClient._nested_payload({"a": 1}, "authed_user") == {}
    assert OAuth2TokenClient._nested_payload({"authed_user": {"access_token": "t"}}, "authed_user") == {
        "access_token": "t"
    }


def test_token_client_config_from_mapping_validates_required_fields():
    cfg = OAuthTokenClientConfig.from_mapping(
        {
            "token_url": " https://auth.example.test/token ",
            "client_id": " synthetic-client ",
            "client_secret": "synthetic-secret",
            "token_auth_method": TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC,
            "token_response_path": " authed_user ",
        }
    )
    assert cfg.token_url == "https://auth.example.test/token"
    assert cfg.client_id == "synthetic-client"
    assert cfg.token_auth_method == TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC
    assert cfg.token_response_path == "authed_user"

    with pytest.raises(ValidationError, match="token_url and client_id"):
        OAuthTokenClientConfig.from_mapping({"token_url": "", "client_id": "synthetic-client"})


def test_build_authorize_url_preserves_existing_query_and_custom_scope_param():
    url = build_authorize_url(
        "https://auth.example.test/authorize?audience=warehouse&state=stale",
        client_id="synthetic-client",
        redirect_uri="https://api.example.test/integrations/oauth/callback",
        state="state-token",
        code_challenge="challenge-token",
        scopes=["sql", "offline_access"],
        scope_param="user_scope",
        extra_params={"prompt": "consent"},
    )
    assert "audience=warehouse" in url
    assert "state=stale" not in url
    assert url.count("state=") == 1
    assert "user_scope=sql+offline_access" in url
    assert "code_challenge_method=S256" in url
    assert "prompt=consent" in url


@pytest.mark.parametrize("protected_key", ["state", "client_id", "redirect_uri", "code_challenge", "scope"])
def test_build_authorize_url_rejects_protected_extra_params(protected_key):
    with pytest.raises(ValidationError, match="cannot override"):
        build_authorize_url(
            "https://auth.example.test/authorize",
            client_id="synthetic-client",
            redirect_uri="https://api.example.test/integrations/oauth/callback",
            state="state-token",
            code_challenge="challenge-token",
            scopes=["sql"],
            extra_params={protected_key: "attacker-controlled"},
        )
