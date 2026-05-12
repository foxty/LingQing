"""Fake OIDC adapter for integration tests."""

from __future__ import annotations

from contextlib import asynccontextmanager

from apps.shared.core.exceptions import AuthenticationError, ValidationError
from apps.shared.external_identity.domain import ExtractedIdentity
from apps.tenant_app_service.sso.domain import ProviderConfig


def _null_http_factory():
    @asynccontextmanager
    async def _client():
        yield None

    return _client()


class FakeOidcAdapter:
    """In-memory OIDC adapter; skips network and JWT crypto."""

    provider_type = "oidc"

    def __init__(self) -> None:
        self.next_identity: ExtractedIdentity | None = None
        self._http_factory = _null_http_factory

    def set_next_identity(
        self,
        *,
        external_subject: str,
        email: str | None,
        display_name: str | None = None,
    ) -> None:
        self.next_identity = ExtractedIdentity(
            external_subject=external_subject,
            email=email,
            display_name=display_name,
        )

    async def _with_client(self):
        return self._http_factory()

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
        if not config.authorize_endpoint:
            raise ValidationError(
                "authorize_endpoint must be pre-fetched via discovery before building the URL",
                {"code": "SSO_DISCOVERY_REQUIRED"},
            )
        return f"{config.authorize_endpoint}?state={state}&nonce={nonce}"

    async def exchange_code(
        self,
        *,
        config: ProviderConfig,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> dict:
        return {"access_token": "fake-access-token", "id_token": "fake.header.fake"}

    async def extract_identity(
        self,
        *,
        config: ProviderConfig,
        token_response: dict,
        expected_nonce: str,
    ) -> ExtractedIdentity:
        if self.next_identity is None:
            raise AuthenticationError("Fake OIDC has no identity configured", {"code": "SSO_FAKE_NO_IDENTITY"})
        return self.next_identity
