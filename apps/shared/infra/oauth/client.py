"""OAuth 2.0 token endpoint adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from apps.shared.core.exceptions import ValidationError
from apps.shared.infra.oauth.constants import TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC
from apps.shared.infra.oauth.models import OAuthTokenEndpointConfig, OAuthTokenSet


class OAuth2TokenClient:
    async def exchange_code(
        self,
        *,
        config: OAuthTokenEndpointConfig,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OAuthTokenSet:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
        }
        return await self._request_token(config=config, data=data)

    async def refresh(
        self,
        *,
        config: OAuthTokenEndpointConfig,
        refresh_token: str,
    ) -> OAuthTokenSet:
        return await self._request_token(
            config=config,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    async def _request_token(
        self,
        *,
        config: OAuthTokenEndpointConfig,
        data: dict[str, str],
    ) -> OAuthTokenSet:
        request_data = {**data, "client_id": config.client_id}
        auth = None
        if config.client_secret:
            if config.token_auth_method == TOKEN_AUTH_METHOD_CLIENT_SECRET_BASIC:
                auth = aiohttp.BasicAuth(config.client_id, config.client_secret)
            else:
                request_data["client_secret"] = config.client_secret

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(config.token_url, data=request_data, auth=auth) as response:
                payload = await self._response_payload(response)
                if response.status < 200 or response.status >= 300:
                    raise ValidationError(f"OAuth token endpoint returned HTTP {response.status}")

        token_payload = self._nested_payload(payload, config.token_response_path)
        error = token_payload.get("error") or payload.get("error")
        if error:
            raise ValidationError(f"OAuth token exchange failed: {error}")
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValidationError("OAuth token response did not include access_token")

        expires_at = None
        expires_in = token_payload.get("expires_in")
        if expires_in is not None:
            try:
                expires_at = datetime.now(UTC) + timedelta(seconds=max(int(expires_in), 0))
            except (TypeError, ValueError):
                expires_at = None

        # Providers like Slack report token_type "user"; HTTP Authorization uses Bearer.
        raw_token_type = token_payload.get("token_type")
        token_type = "Bearer"
        if isinstance(raw_token_type, str) and raw_token_type.strip().lower() == "bearer":
            token_type = "Bearer"

        return OAuthTokenSet(
            access_token=access_token,
            refresh_token=token_payload.get("refresh_token"),
            token_type=token_type,
            expires_at=expires_at,
            scopes=token_payload.get("scope"),
        )

    @staticmethod
    async def _response_payload(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except Exception as exc:
            raise ValidationError("OAuth token endpoint returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise ValidationError("OAuth token endpoint returned an invalid response")
        return payload

    @staticmethod
    def _nested_payload(payload: dict[str, Any], path: str | None) -> dict[str, Any]:
        current: Any = payload
        if path:
            for part in path.split("."):
                if not isinstance(current, dict):
                    break
                current = current.get(part)
        return current if isinstance(current, dict) else {}
