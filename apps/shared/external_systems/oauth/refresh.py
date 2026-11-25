"""Resource-agnostic OAuth 2.0 user token refresh policy."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.shared.core.exceptions import IntegrationNotConnectedError, ValidationError
from apps.shared.infra.oauth import (
    OAuth2TokenClient,
    OAuthTokenClientConfig,
    OAuthTokenSet,
)

REFRESH_LEEWAY_SECONDS = 60


def is_oauth_refresh_due(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    normalized = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at.astimezone(UTC)
    return normalized <= datetime.now(UTC) + timedelta(seconds=REFRESH_LEEWAY_SECONDS)


async def maybe_refresh_oauth2_secrets(
    *,
    auth_type: str | None,
    oauth_template: Mapping[str, Any],
    user_secrets: dict[str, Any],
    expires_at: datetime | None,
    resource_type: str,
    token_client: OAuth2TokenClient | None = None,
) -> OAuthTokenSet | None:
    """Refresh user OAuth2 tokens when near/past expiry; return ``None`` when still fresh."""
    if not is_oauth_refresh_due(expires_at):
        return None

    refresh_token = user_secrets.get("refresh_token")
    if auth_type != "oauth2" or not isinstance(refresh_token, str) or not refresh_token.strip():
        raise IntegrationNotConnectedError(
            "Integration credentials expired; reconnect to continue",
            {"code": "INTEGRATION_CREDENTIAL_EXPIRED", "resource_type": resource_type},
        )

    try:
        # Endpoint and client configuration is administrator-controlled. Never
        # allow user credential payloads to override where shared secrets are sent.
        endpoint_config = OAuthTokenClientConfig.from_mapping(oauth_template)
    except ValidationError as exc:
        raise IntegrationNotConnectedError(
            "Invalid OAuth2 integration configuration",
            {"code": "INTEGRATION_OAUTH_CONFIG_INVALID", "resource_type": resource_type},
        ) from exc

    client = token_client or OAuth2TokenClient()
    return await client.refresh(
        config=endpoint_config,
        refresh_token=refresh_token,
    )
