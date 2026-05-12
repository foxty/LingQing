"""JWT token issuer adapter.

Implements the `TokenIssuer` port defined in the auth domain. Both native and
SSO login depend on this so token claims + expiry have a single source.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import jwt

from apps.config import get_settings


class JwtTokenIssuer:
    """Issues HS-signed JWTs using app SECRET_KEY / ALGORITHM / expiry."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def issue(
        self,
        *,
        user_id: int,
        username: str,
        role: str,
        tenant_id: int,
        tenant_name: str,
    ) -> str:
        expires = datetime.now(UTC) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": username,
            "user_id": user_id,
            "role": role,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "exp": expires,
        }
        return jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm=self.settings.ALGORITHM)
