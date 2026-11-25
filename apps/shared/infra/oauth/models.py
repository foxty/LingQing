"""OAuth 2.0 token models and endpoint config protocol."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from apps.shared.core.exceptions import ValidationError
from apps.shared.infra.oauth.constants import (
    TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC,
    TOKEN_AUTH_METHOD_CLIENT_SECRET_POST,
)


@dataclass(frozen=True)
class OAuthTokenSet:
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_at: datetime | None
    scopes: str | None = None

    def to_secrets(self) -> dict[str, str]:
        values = {
            "access_token": self.access_token,
            "token_type": self.token_type,
        }
        if self.refresh_token:
            values["refresh_token"] = self.refresh_token
        if self.scopes:
            values["scope"] = self.scopes
        return values


@runtime_checkable
class OAuthTokenEndpointConfig(Protocol):
    """Minimal token-endpoint shape used by ``OAuth2TokenClient``.

    Product configs (API connector, data source, Drive, SSO) can satisfy this structurally.
    """

    token_url: str
    client_id: str
    client_secret: str | None
    token_auth_method: str
    token_response_path: str | None


@dataclass(frozen=True)
class OAuthTokenClientConfig:
    """Concrete ``OAuthTokenEndpointConfig`` value object for protocol callers."""

    token_url: str
    client_id: str
    client_secret: str | None = None
    token_auth_method: str = TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
    token_response_path: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> OAuthTokenClientConfig:
        token_url = str(raw.get("token_url") or "").strip()
        client_id = str(raw.get("client_id") or "").strip()
        if not token_url or not client_id:
            raise ValidationError("OAuth token configuration requires token_url and client_id")
        raw_secret = raw.get("client_secret")
        client_secret = str(raw_secret) if isinstance(raw_secret, str) and raw_secret else None
        method = str(raw.get("token_auth_method") or TOKEN_AUTH_METHOD_CLIENT_SECRET_POST)
        if method not in {TOKEN_AUTH_METHOD_CLIENT_SECRET_POST, TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC}:
            method = TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
        raw_path = raw.get("token_response_path")
        response_path = str(raw_path).strip() if isinstance(raw_path, str) and raw_path.strip() else None
        return cls(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            token_auth_method=method,
            token_response_path=response_path,
        )
