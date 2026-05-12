"""Integration tests for OIDC SSO start/callback/exchange flows."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from tests.integration.conftest import make_auth_headers
from tests.integration.helpers.sso_helpers import (
    callback_sso,
    configure_oidc_identity,
    create_oidc_provider,
    exchange_sso_ticket,
    start_sso,
    ticket_from_redirect,
)


class TestSsoLoginFlow:
    @pytest.mark.asyncio
    async def test_start_returns_authorize_url(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        provider = await create_oidc_provider(client, tenant["token"], enabled=True)

        state, url = await start_sso(
            client,
            tenant_id=tenant["tenant"].id,
            provider_id=provider["id"],
        )
        assert state
        assert "fake-idp.test/authorize" in url

    @pytest.mark.asyncio
    async def test_disabled_provider_start_returns_404(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        provider = await create_oidc_provider(client, tenant["token"], enabled=False)

        resp = await client.get(
            f"/auth/sso/{provider['id']}/start",
            params={"tenant_id": tenant["tenant"].id},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_jit_create_issues_login_ticket(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        domains_resp = await client.get("/tenants/identity/domains", headers=make_auth_headers(tenant["token"]))
        allowed_domain = domains_resp.json()[0]["domain"]
        email = f"jit_{uuid4().hex[:8]}@{allowed_domain}"
        subject = f"oidc-sub-{uuid4().hex[:8]}"

        provider = await create_oidc_provider(
            client,
            tenant["token"],
            enabled=True,
            first_login_policy="jit_create",
        )
        state, _ = await start_sso(client, tenant_id=tenant["tenant"].id, provider_id=provider["id"])
        configure_oidc_identity(fake_oidc_adapter, external_subject=subject, email=email, display_name="JIT User")

        location = await callback_sso(client, state=state)
        assert "status=pending" not in location
        assert "status=denied" not in location

        ticket = ticket_from_redirect(location)
        exchange = await exchange_sso_ticket(client, ticket)
        assert exchange["access_token"]
        assert exchange["tenant_id"] == tenant["tenant"].id

    @pytest.mark.asyncio
    async def test_existing_email_attaches_and_logs_in(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        admin = tenant["admin"]
        subject = f"oidc-sub-{uuid4().hex[:8]}"

        provider = await create_oidc_provider(client, tenant["token"], enabled=True)
        state, _ = await start_sso(client, tenant_id=tenant["tenant"].id, provider_id=provider["id"])
        configure_oidc_identity(
            fake_oidc_adapter,
            external_subject=subject,
            email=admin.email,
            display_name=admin.username,
        )

        location = await callback_sso(client, state=state)
        ticket = ticket_from_redirect(location)
        exchange = await exchange_sso_ticket(client, ticket)
        assert exchange["user_id"] == admin.id

    @pytest.mark.asyncio
    async def test_pending_approval_redirects_to_pending(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        domains_resp = await client.get("/tenants/identity/domains", headers=make_auth_headers(tenant["token"]))
        allowed_domain = domains_resp.json()[0]["domain"]
        email = f"pending_{uuid4().hex[:8]}@{allowed_domain}"
        subject = f"oidc-sub-{uuid4().hex[:8]}"

        provider = await create_oidc_provider(
            client,
            tenant["token"],
            enabled=True,
            first_login_policy="pending_approval",
        )
        state, _ = await start_sso(client, tenant_id=tenant["tenant"].id, provider_id=provider["id"])
        configure_oidc_identity(fake_oidc_adapter, external_subject=subject, email=email)

        location = await callback_sso(client, state=state)
        assert "status=pending" in location

        pending_resp = await client.get("/tenants/identity/pending", headers=make_auth_headers(tenant["token"]))
        assert any(p["external_subject"] == subject for p in pending_resp.json())

    @pytest.mark.asyncio
    async def test_reject_unknown_denies_callback(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        domains_resp = await client.get("/tenants/identity/domains", headers=make_auth_headers(tenant["token"]))
        allowed_domain = domains_resp.json()[0]["domain"]
        email = f"reject_{uuid4().hex[:8]}@{allowed_domain}"
        subject = f"oidc-sub-{uuid4().hex[:8]}"

        provider = await create_oidc_provider(
            client,
            tenant["token"],
            enabled=True,
            first_login_policy="reject_unknown",
        )
        state, _ = await start_sso(client, tenant_id=tenant["tenant"].id, provider_id=provider["id"])
        configure_oidc_identity(fake_oidc_adapter, external_subject=subject, email=email)

        location = await callback_sso(client, state=state)
        assert "status=denied" in location

    @pytest.mark.asyncio
    async def test_domain_not_allowed_denies_callback(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        subject = f"oidc-sub-{uuid4().hex[:8]}"

        provider = await create_oidc_provider(client, tenant["token"], enabled=True)
        state, _ = await start_sso(client, tenant_id=tenant["tenant"].id, provider_id=provider["id"])
        configure_oidc_identity(
            fake_oidc_adapter,
            external_subject=subject,
            email=f"blocked_{uuid4().hex[:8]}@not-allowed.example",
        )

        location = await callback_sso(client, state=state)
        query = parse_qs(urlparse(location).query)
        assert query.get("status", [""])[0] == "denied"

    @pytest.mark.asyncio
    async def test_callback_after_provider_disabled_is_denied(self, slack_test_setup, fake_oidc_adapter):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        admin = tenant["admin"]
        subject = f"oidc-sub-{uuid4().hex[:8]}"

        provider = await create_oidc_provider(client, tenant["token"], enabled=True)
        state, _ = await start_sso(client, tenant_id=tenant["tenant"].id, provider_id=provider["id"])

        disable_resp = await client.post(
            f"/tenants/auth-providers/{provider['id']}/disable",
            headers=make_auth_headers(tenant["token"]),
        )
        assert disable_resp.status_code == 200

        configure_oidc_identity(fake_oidc_adapter, external_subject=subject, email=admin.email)
        location = await callback_sso(client, state=state)
        assert "status=denied" in location
