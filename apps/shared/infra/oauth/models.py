"""OAuth 2.0 token models and endpoint config protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


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

    Product configs (API connector, Drive, SSO) can satisfy this structurally.
    """

    token_url: str
    client_id: str
    client_secret: str | None
    token_auth_method: str
    token_response_path: str | None
