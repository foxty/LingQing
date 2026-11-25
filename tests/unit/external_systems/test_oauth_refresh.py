"""Unit tests for shared OAuth refresh policy (``refresh.py``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from apps.shared.core.exceptions import IntegrationNotConnectedError, ValidationError
from apps.shared.external_systems.oauth.refresh import (
    REFRESH_LEEWAY_SECONDS,
    is_oauth_refresh_due,
    maybe_refresh_oauth2_secrets,
)
from apps.shared.infra.oauth import OAuthTokenSet


def test_is_oauth_refresh_due_false_when_expires_at_missing():
    assert is_oauth_refresh_due(None) is False


def test_is_oauth_refresh_due_false_when_well_before_expiry():
    assert is_oauth_refresh_due(datetime.now(UTC) + timedelta(hours=2)) is False


def test_is_oauth_refresh_due_true_when_past_expiry():
    assert is_oauth_refresh_due(datetime.now(UTC) - timedelta(seconds=5)) is True


def test_is_oauth_refresh_due_true_within_leeway_window():
    assert is_oauth_refresh_due(
        datetime.now(UTC) + timedelta(seconds=max(REFRESH_LEEWAY_SECONDS - 1, 0))
    ) is True


def test_is_oauth_refresh_due_treats_naive_datetime_as_utc():
    naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    assert is_oauth_refresh_due(naive) is True


@pytest.mark.asyncio
async def test_maybe_refresh_oauth2_secrets_returns_none_when_still_fresh():
    tokens = await maybe_refresh_oauth2_secrets(
        auth_type="oauth2",
        oauth_template={
            "token_url": "https://auth.example.test/token",
            "client_id": "synthetic-client",
        },
        user_secrets={"access_token": "access", "refresh_token": "refresh"},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        resource_type="api_connector",
    )
    assert tokens is None


@pytest.mark.asyncio
async def test_maybe_refresh_oauth2_secrets_raises_when_refresh_token_missing():
    with pytest.raises(IntegrationNotConnectedError, match="expired"):
        await maybe_refresh_oauth2_secrets(
            auth_type="oauth2",
            oauth_template={
                "token_url": "https://auth.example.test/token",
                "client_id": "synthetic-client",
            },
            user_secrets={"access_token": "access"},
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            resource_type="api_connector",
        )


@pytest.mark.asyncio
async def test_maybe_refresh_oauth2_secrets_raises_on_invalid_oauth_template():
    with pytest.raises(IntegrationNotConnectedError, match="Invalid OAuth2"):
        await maybe_refresh_oauth2_secrets(
            auth_type="oauth2",
            oauth_template={"token_url": "", "client_id": "synthetic-client"},
            user_secrets={"access_token": "access", "refresh_token": "refresh"},
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            resource_type="api_connector",
        )


@pytest.mark.asyncio
async def test_maybe_refresh_oauth2_secrets_uses_template_not_user_secrets_for_endpoints():
    refreshed = OAuthTokenSet(
        access_token="new-access",
        refresh_token="new-refresh",
        token_type="Bearer",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    client = AsyncMock()
    client.refresh = AsyncMock(return_value=refreshed)

    result = await maybe_refresh_oauth2_secrets(
        auth_type="oauth2",
        oauth_template={
            "token_url": "https://auth.example.test/token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
        },
        user_secrets={
            "access_token": "access",
            "refresh_token": "user-refresh",
            "token_url": "https://attacker.example.test/token",
            "client_id": "attacker-client",
        },
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        resource_type="api_connector",
        token_client=client,
    )

    assert result == refreshed
    client.refresh.assert_awaited_once()
    refresh_config = client.refresh.await_args.kwargs["config"]
    assert refresh_config.token_url == "https://auth.example.test/token"
    assert refresh_config.client_id == "synthetic-client"
    assert client.refresh.await_args.kwargs["refresh_token"] == "user-refresh"


@pytest.mark.asyncio
async def test_maybe_refresh_oauth2_secrets_wraps_validation_error_from_config():
    with pytest.raises(IntegrationNotConnectedError) as exc_info:
        await maybe_refresh_oauth2_secrets(
            auth_type="oauth2",
            oauth_template={"client_id": "only-client-id"},
            user_secrets={"access_token": "access", "refresh_token": "refresh"},
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            resource_type="api_connector",
        )
    assert exc_info.value.details.get("code") == "INTEGRATION_OAUTH_CONFIG_INVALID"
    assert isinstance(exc_info.value.__cause__, ValidationError)