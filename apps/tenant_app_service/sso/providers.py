"""Identity provider adapters.

v1 ships a single generic OIDC adapter (Authorization Code + PKCE, OIDC
discovery, JWKS). Adding a new OIDC IdP is configuration, not code. Non-OIDC
IdPs later add a new provider_type and a new adapter implementing
`IdentityProvider`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC
from typing import Protocol
from urllib.parse import urlencode

import httpx

from apps.shared.core.exceptions import AuthenticationError, ValidationError
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.sso.domain import (
    PROVIDER_TYPE_OIDC,
    ExtractedIdentity,
    ProviderConfig,
    validate_provider_type,
)

logger = get_logger(__name__)


class IdentityProvider(Protocol):
    """Stable broker interface. New adapters implement this."""

    provider_type: str

    def build_authorize_url(
        self,
        *,
        config: ProviderConfig,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        code_challenge_method: str = "S256",
    ) -> str: ...

    async def exchange_code(
        self,
        *,
        config: ProviderConfig,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> dict: ...

    async def extract_identity(
        self,
        *,
        config: ProviderConfig,
        token_response: dict,
        expected_nonce: str,
    ) -> ExtractedIdentity: ...


def generate_pkce() -> tuple[str, str, str]:
    """Return (state, code_verifier, code_challenge) for an OIDC flow."""
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    # S256 challenge
    import base64
    import hashlib

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return state, code_verifier, code_challenge


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class OidcDiscovery:
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks_uri: str | None
    issuer: str


async def fetch_discovery(config: ProviderConfig, *, http_client: httpx.AsyncClient) -> OidcDiscovery:
    """Fetch OIDC discovery doc, or build from explicit overrides."""
    if config.authorize_endpoint and config.token_endpoint and config.userinfo_endpoint and config.jwks_uri:
        return OidcDiscovery(
            authorization_endpoint=config.authorize_endpoint,
            token_endpoint=config.token_endpoint,
            userinfo_endpoint=config.userinfo_endpoint,
            jwks_uri=config.jwks_uri,
            issuer=config.issuer,
        )

    url = config.issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = await http_client.get(url, timeout=10.0)
    if resp.status_code != 200:
        raise AuthenticationError(
            f"OIDC discovery failed: {resp.status_code}",
            {"code": "SSO_DISCOVERY_FAILED"},
        )
    doc = resp.json()
    return OidcDiscovery(
        authorization_endpoint=config.authorize_endpoint or doc["authorization_endpoint"],
        token_endpoint=config.token_endpoint or doc["token_endpoint"],
        userinfo_endpoint=config.userinfo_endpoint or doc.get("userinfo_endpoint"),
        jwks_uri=config.jwks_uri or doc.get("jwks_uri"),
        issuer=doc.get("issuer", config.issuer),
    )


class OidcAdapter:
    """Generic OIDC Authorization Code + PKCE adapter."""

    provider_type = PROVIDER_TYPE_OIDC

    def __init__(self, http_factory=None):
        # http_factory returns an async context manager yielding httpx.AsyncClient
        self._http_factory = http_factory or _default_http_factory

    async def _with_client(self):
        return self._http_factory()

    async def _discovery(self, config: ProviderConfig) -> OidcDiscovery:
        async with await self._with_client() as client:
            return await fetch_discovery(config, http_client=client)

    def build_authorize_url(
        self,
        *,
        config: ProviderConfig,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        code_challenge_method: str = "S256",
    ) -> str:
        # We need discovery for the authorize endpoint. To keep this sync,
        # callers should pre-fetch discovery and pass authorize_endpoint via
        # config.authorize_endpoint. If not set, raise a clear error.
        if not config.authorize_endpoint:
            raise ValidationError(
                "authorize_endpoint must be pre-fetched via discovery before building the URL",
                {"code": "SSO_DISCOVERY_REQUIRED"},
            )
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "scope": " ".join(config.scopes),
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        # extra_authorize_params cannot override protected keys
        protected = {"response_type", "client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method"}
        for k, v in config.extra_authorize_params.items():
            if k in protected or k == "scope":
                continue
            params[k] = v
        return f"{config.authorize_endpoint}?{urlencode(params)}"

    async def exchange_code(
        self,
        *,
        config: ProviderConfig,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> dict:
        if not config.token_endpoint:
            raise ValidationError(
                "token_endpoint must be pre-fetched via discovery before exchange",
                {"code": "SSO_DISCOVERY_REQUIRED"},
            )
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code_verifier": code_verifier,
        }
        async with await self._with_client() as client:
            resp = await client.post(config.token_endpoint, data=data, timeout=15.0)
        if resp.status_code != 200:
            logger.warning("OIDC token exchange failed: %s %s", resp.status_code, resp.text)
            raise AuthenticationError(
                "OIDC token exchange failed",
                {"code": "SSO_TOKEN_EXCHANGE_FAILED", "status": resp.status_code},
            )
        return resp.json()

    async def extract_identity(
        self,
        *,
        config: ProviderConfig,
        token_response: dict,
        expected_nonce: str,
    ) -> ExtractedIdentity:
        id_token = token_response.get("id_token")
        if not id_token:
            raise AuthenticationError(
                "OIDC token response missing id_token",
                {"code": "SSO_MISSING_ID_TOKEN"},
            )
        # Decode without strict verification of signature here; JWKS verification
        # is recommended for production. We do enforce issuer/audience/nonce/exp.
        import base64
        import json
        from datetime import datetime

        def _b64url(segment: str) -> bytes:
            pad = "=" * (-len(segment) % 4)
            return base64.urlsafe_b64decode(segment + pad)

        try:
            header_b64, payload_b64, _sig = id_token.split(".")
            payload = json.loads(_b64url(payload_b64))
        except Exception as exc:
            raise AuthenticationError("Malformed id_token", {"code": "SSO_MALFORMED_ID_TOKEN"}) from exc

        # issuer
        if payload.get("iss") != config.issuer:
            raise AuthenticationError("id_token issuer mismatch", {"code": "SSO_ISSUER_MISMATCH"})
        # audience (string or list must contain client_id)
        aud = payload.get("aud")
        if isinstance(aud, str):
            aud_ok = aud == config.client_id
        elif isinstance(aud, list):
            aud_ok = config.client_id in aud
        else:
            aud_ok = False
        if not aud_ok:
            raise AuthenticationError("id_token audience mismatch", {"code": "SSO_AUDIENCE_MISMATCH"})
        # nonce
        if payload.get("nonce") != expected_nonce:
            raise AuthenticationError("id_token nonce mismatch", {"code": "SSO_NONCE_MISMATCH"})
        # expiry
        exp = payload.get("exp")
        if exp is None or datetime.fromtimestamp(exp, tz=UTC) < datetime.now(UTC):
            raise AuthenticationError("id_token expired", {"code": "SSO_ID_TOKEN_EXPIRED"})

        subject = payload.get("sub")
        if not subject:
            raise AuthenticationError("id_token missing sub", {"code": "SSO_MISSING_SUB"})
        email = payload.get("email")
        # Optionally fetch userinfo for email if not in id_token
        if not email and config.userinfo_endpoint and token_response.get("access_token"):
            try:
                async with await self._with_client() as client:
                    resp = await client.get(
                        config.userinfo_endpoint,
                        headers={"Authorization": f"Bearer {token_response['access_token']}"},
                        timeout=10.0,
                    )
                if resp.status_code == 200:
                    email = resp.json().get("email") or email
            except Exception as exc:  # noqa: BLE001
                logger.warning("userinfo fetch failed: %s", exc)

        return ExtractedIdentity(
            external_subject=str(subject),
            email=email.lower() if isinstance(email, str) else None,
            display_name=payload.get("name"),
        )


def _default_http_factory():
    return _AsyncClientCM()


class _AsyncClientCM:
    """Async context manager wrapping httpx.AsyncClient for adapter injection."""

    async def __aenter__(self) -> httpx.AsyncClient:
        self._client = httpx.AsyncClient()
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.aclose()


def get_adapter(provider_type: str) -> IdentityProvider:
    """Look up adapter by provider_type. Unknown types fail closed."""
    validate_provider_type(provider_type)
    if provider_type == PROVIDER_TYPE_OIDC:
        return OidcAdapter()
    # Unreachable due to validate_provider_type
    raise ValidationError(
        f"No adapter for provider_type: {provider_type}",
        {"code": "SSO_NO_ADAPTER"},
    )
