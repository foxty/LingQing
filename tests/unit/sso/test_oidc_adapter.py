"""Unit tests for the generic OIDC adapter security invariants.

Locks PKCE S256, nonce, issuer/audience/expiry checks, and protected
authorize-URL params. No network: id_token payloads are crafted locally.
"""

import base64
import hashlib
import json
import time

import pytest

from apps.shared.core.exceptions import AuthenticationError, ValidationError
from apps.tenant_app_service.sso.domain import ProviderConfig
from apps.tenant_app_service.sso.providers import (
    OidcAdapter,
    generate_nonce,
    generate_pkce,
    get_adapter,
)


def _config(**overrides) -> ProviderConfig:
    base = dict(
        client_id="cid",
        client_secret="sec",
        issuer="https://idp.example",
        scopes=["openid", "email", "profile"],
        authorize_endpoint="https://idp.example/authorize",
        token_endpoint="https://idp.example/token",
        userinfo_endpoint=None,
        jwks_uri=None,
        extra_authorize_params={},
    )
    base.update(overrides)
    return ProviderConfig(**base)


def _b64url(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _id_token(payload: dict) -> str:
    header = _b64url({"alg": "RS256", "typ": "JWT"})
    body = _b64url(payload)
    return f"{header}.{body}.sig"


# ---------- PKCE ----------


def test_pkce_returns_three_distinct_random_values():
    state, verifier, challenge = generate_pkce()
    assert state and verifier and challenge
    assert state != verifier != challenge


def test_pkce_challenge_is_s256_of_verifier():
    _, verifier, challenge = generate_pkce()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_pkce_state_is_high_entropy():
    a = generate_pkce()
    b = generate_pkce()
    assert a[0] != b[0]


def test_generate_nonce_is_random():
    assert generate_nonce() != generate_nonce()


# ---------- Authorize URL ----------


def test_authorize_url_contains_required_params():
    cfg = _config()
    url = OidcAdapter().build_authorize_url(
        config=cfg,
        redirect_uri="https://app/callback",
        state="STATE",
        nonce="NONCE",
        code_challenge="CHALLENGE",
    )
    assert url.startswith("https://idp.example/authorize?")
    assert "response_type=code" in url
    assert "client_id=cid" in url
    assert "redirect_uri=https" in url
    assert "state=STATE" in url
    assert "nonce=NONCE" in url
    assert "code_challenge=CHALLENGE" in url
    assert "code_challenge_method=S256" in url
    assert "scope=openid+email+profile" in url


def test_authorize_url_rejects_protected_param_overrides():
    cfg = _config(
        extra_authorize_params={
            "client_id": "evil",
            "state": "evil",
            "code_challenge": "evil",
            "redirect_uri": "https://evil",
            "scope": "evil",
            "prompt": "login",  # allowed
        }
    )
    url = OidcAdapter().build_authorize_url(
        config=cfg,
        redirect_uri="https://app/callback",
        state="STATE",
        nonce="NONCE",
        code_challenge="CHALLENGE",
    )
    assert "client_id=cid" in url
    assert "state=STATE" in url
    assert "code_challenge=CHALLENGE" in url
    assert "redirect_uri=https%3A%2F%2Fapp%2Fcallback" in url
    assert "scope=openid" in url
    assert "prompt=login" in url  # extra allowed


def test_authorize_url_requires_discovery_first():
    cfg = _config(authorize_endpoint=None)
    with pytest.raises(ValidationError):
        OidcAdapter().build_authorize_url(
            config=cfg,
            redirect_uri="https://app/callback",
            state="S",
            nonce="N",
            code_challenge="C",
        )


# ---------- id_token validation ----------


def _payload(**overrides) -> dict:
    base = dict(
        iss="https://idp.example",
        aud="cid",
        sub="sub-1",
        email="alice@company.com",
        nonce="NONCE",
        exp=int(time.time()) + 600,
        name="Alice",
    )
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_extract_identity_success():
    cfg = _config()
    token = {"id_token": _id_token(_payload())}
    ident = await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")
    assert ident.external_subject == "sub-1"
    assert ident.email == "alice@company.com"
    assert ident.display_name == "Alice"


@pytest.mark.asyncio
async def test_extract_identity_rejects_issuer_mismatch():
    cfg = _config()
    token = {"id_token": _id_token(_payload(iss="https://evil"))}
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")


@pytest.mark.asyncio
async def test_extract_identity_rejects_audience_mismatch():
    cfg = _config()
    token = {"id_token": _id_token(_payload(aud="other-client"))}
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")


@pytest.mark.asyncio
async def test_extract_identity_accepts_audience_list():
    cfg = _config()
    token = {"id_token": _id_token(_payload(aud=["other", "cid"]))}
    ident = await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")
    assert ident.external_subject == "sub-1"


@pytest.mark.asyncio
async def test_extract_identity_rejects_nonce_mismatch():
    cfg = _config()
    token = {"id_token": _id_token(_payload(nonce="WRONG"))}
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")


@pytest.mark.asyncio
async def test_extract_identity_rejects_expired_token():
    cfg = _config()
    token = {"id_token": _id_token(_payload(exp=int(time.time()) - 1))}
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")


@pytest.mark.asyncio
async def test_extract_identity_rejects_missing_sub():
    cfg = _config()
    token = {"id_token": _id_token(_payload(sub=None))}
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")


@pytest.mark.asyncio
async def test_extract_identity_rejects_missing_id_token():
    cfg = _config()
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(config=cfg, token_response={}, expected_nonce="NONCE")


@pytest.mark.asyncio
async def test_extract_identity_rejects_malformed_id_token():
    cfg = _config()
    with pytest.raises(AuthenticationError):
        await OidcAdapter().extract_identity(
            config=cfg, token_response={"id_token": "not.a.jwt"}, expected_nonce="NONCE"
        )


@pytest.mark.asyncio
async def test_extract_identity_lowercases_email():
    cfg = _config()
    token = {"id_token": _id_token(_payload(email="Alice@Company.COM"))}
    ident = await OidcAdapter().extract_identity(config=cfg, token_response=token, expected_nonce="NONCE")
    assert ident.email == "alice@company.com"


# ---------- Adapter lookup ----------


def test_get_adapter_returns_oidc():
    adapter = get_adapter("oidc")
    assert adapter.provider_type == "oidc"


def test_get_adapter_rejects_unknown_type():
    with pytest.raises(ValidationError):
        get_adapter("saml")
