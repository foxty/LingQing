"""Integration: API connector user OAuth connect + execute with stubbed token/Slack HTTP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apps.shared.db.models import Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.api_connector.domain import RatePolicyDomain
from apps.shared.external_systems.api_connector.execution import ApiConnectorExecutionService
from apps.shared.external_systems.api_connector.schemas import ApiOperationCallParameters
from apps.shared.external_systems.api_connector.service import ApiConnectorService
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.domain.types import USER_CONNECTION_CONNECTED
from apps.shared.external_systems.oauth.flow import ApiConnectorOAuthFlow
from apps.shared.infra.oauth import OAuthTokenSet
from apps.shared.utils.field_cipher import FieldCipher


@pytest.mark.asyncio
async def test_oauth_start_callback_marks_connector_connected(async_db_session, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"oauth_flow_{suffix}", slug=f"oauth-flow-{suffix}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username=f"oauth_user_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name=f"slack-oauth-{suffix}",
        description=None,
        base_url="https://slack.com/api",
        auth_type="oauth2",
        auth_config={
            "auth_method": "oauth2",
            "authorize_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "scopes": ["search:read"],
            "scope_param": "user_scope",
            "token_response_path": "authed_user",
            "redirect_uri": "https://api.example.test/api-connectors/oauth/callback",
        },
        rate_policy=RatePolicyDomain(),
        schema_source_type="manual",
        schema_source_url=None,
        credential_mode="user",
    )

    flow = ApiConnectorOAuthFlow(async_db_session)
    authorize_url = await flow.start(actor=actor, connector_id=connector.id)
    assert "client_id=synthetic-client" in authorize_url
    assert "code_challenge=" in authorize_url
    assert "user_scope=search%3Aread" in authorize_url or "user_scope=search:read" in authorize_url

    from urllib.parse import parse_qs, urlsplit

    state = parse_qs(urlsplit(authorize_url).query)["state"][0]

    exchange = AsyncMock(
        return_value=OAuthTokenSet(
            access_token="xoxp-connected-token",
            refresh_token="xoxe-refresh",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes="search:read",
        )
    )
    flow._token_client.exchange_code = exchange

    resolved_id = await flow.complete_from_callback(code="auth-code", state=state)
    assert resolved_id == connector.id
    exchange.assert_awaited_once()

    enriched = await service.get_connector_for_actor(connector_id=connector.id, actor=actor)
    assert enriched.user_connection_status == USER_CONNECTION_CONNECTED


@pytest.mark.asyncio
async def test_oauth2_user_binding_executes_search_messages_with_bearer(async_db_session, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"oauth_exec_{suffix}", slug=f"oauth-exec-{suffix}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username=f"oauth_exec_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name=f"slack-exec-{suffix}",
        description=None,
        base_url="https://slack.com/api",
        auth_type="oauth2",
        auth_config={
            "auth_method": "oauth2",
            "authorize_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "scopes": ["search:read"],
        },
        rate_policy=RatePolicyDomain.from_raw({"timeout_ms": 5000}),
        schema_source_type="manual",
        schema_source_url=None,
        credential_mode="user",
    )
    operation = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=actor,
        method="POST",
        path_template="/search.messages",
        operation_id="slack_search_messages",
        summary="Search",
        description=None,
        tags=["slack"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    cipher = FieldCipher()
    repo = UserIntegrationCredentialRepository(async_db_session)
    await repo.upsert_binding(
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector.id,
        auth_type="oauth2",
        secrets_enc=cipher.encrypt_dict(
            {"access_token": "xoxp-exec-token", "token_type": "user"},
            sensitive_fields={"access_token"},
        ),
        account_label="slack-user",
    )

    captured: list[dict] = []

    async def _fake_send(self, *, method, url, headers, query, body, timeout_ms):
        captured.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        return 200, {}, {"ok": True, "messages": {"matches": []}}

    monkeypatch.setattr(ApiConnectorExecutionService, "_send_http_request", _fake_send)

    exec_service = ApiConnectorExecutionService(
        tenant_id=tenant.id,
        db_session=async_db_session,
        user_integration_auth=IntegrationCredentialResolver(async_db_session),
    )
    result = await exec_service.execute_operation_for_actor(
        operation_uid=operation.operation_uid,
        actor=actor,
        parameters=ApiOperationCallParameters(body={"query": "release notes"}),
    )

    assert result.error is None
    assert result.status_code == 200
    assert result.body["ok"] is True
    assert len(captured) == 1
    assert captured[0]["url"].endswith("/search.messages")
    assert captured[0]["headers"].get("Authorization") == "Bearer xoxp-exec-token"


@pytest.mark.asyncio
async def test_expired_oauth_user_token_refresh_persists_binding(async_db_session, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"oauth_ref_{suffix}", slug=f"oauth-ref-{suffix}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username=f"oauth_ref_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name=f"slack-refresh-{suffix}",
        description=None,
        base_url="https://slack.com/api",
        auth_type="oauth2",
        auth_config={
            "auth_method": "oauth2",
            "authorize_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "scopes": ["search:read"],
        },
        rate_policy=RatePolicyDomain(),
        schema_source_type="manual",
        schema_source_url=None,
        credential_mode="user",
    )

    cipher = FieldCipher()
    repo = UserIntegrationCredentialRepository(async_db_session)
    await repo.upsert_binding(
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector.id,
        auth_type="oauth2",
        secrets_enc=cipher.encrypt_dict(
            {
                "access_token": "xoxp-expired",
                "refresh_token": "xoxe-refresh",
                "token_type": "Bearer",
            },
            sensitive_fields={"access_token", "refresh_token"},
        ),
        account_label="slack-user",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    from apps.shared.infra.oauth import OAuth2TokenClient
    from apps.shared.external_systems.domain.types import IntegrationPurpose

    refresh_calls: list[str] = []

    async def fake_refresh(self, *, config, refresh_token):
        refresh_calls.append(refresh_token)
        assert refresh_token == "xoxe-refresh"
        return OAuthTokenSet(
            access_token="xoxp-refreshed",
            refresh_token="xoxe-refresh-rotated",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

    monkeypatch.setattr(OAuth2TokenClient, "refresh", fake_refresh)

    connector_row = await service.connector_repo.get_by_id_and_tenant(connector.id, tenant.id)
    assert connector_row is not None

    resolver = IntegrationCredentialResolver(async_db_session, cipher=cipher)
    resolved = await resolver.resolve_api_connector_auth_config(
        connector=connector_row,
        actor=actor,
        purpose=IntegrationPurpose.EXECUTE,
    )
    assert resolved["access_token"] == "xoxp-refreshed"
    assert refresh_calls == ["xoxe-refresh"]

    binding = await repo.get_binding(
        tenant_id=tenant.id,
        user_id=user.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector.id,
    )
    assert binding is not None
    secrets = cipher.decrypt_dict(
        binding.secrets_enc,
        sensitive_fields={"access_token", "refresh_token"},
    )
    assert secrets["access_token"] == "xoxp-refreshed"
    assert secrets["refresh_token"] == "xoxe-refresh-rotated"
    assert binding.expires_at is not None
    assert binding.expires_at > datetime.now(UTC)
