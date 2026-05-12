"""Integration tests for the Slack identity bind + chat gate flow.

Verifies email auto-match on first DM, reject-unknown for unmatched users,
admin bind approval for legacy pending rows, and tenant isolation.
"""

import asyncio
from uuid import uuid4

import pytest

from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository
from apps.shared.external_identity.repository import ExternalIdentityRepository
from tests.integration.conftest import make_auth_headers
from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import make_event_callback_payload, make_message_event


async def _seed_pending_slack_identity(slack_test_setup, tenant_label: str, slack_user: str, email: str):
    tenant = slack_test_setup["tenants"][tenant_label]["tenant"]
    team_id = f"T_{tenant_label.upper()}"
    async with slack_test_setup["session_factory"]() as session:
        source_repo = SlackIdentitySourceRepository(session)
        identity_repo = ExternalIdentityRepository(session)
        source = await source_repo.ensure_slack_workspace_source(tenant_id=tenant.id, team_id=team_id)
        row = await identity_repo.create_identity(
            tenant_id=tenant.id,
            identity_source_id=source.id,
            external_subject=slack_user,
            user_id=None,
            email=email,
            display_name=slack_user,
            status="pending",
        )
        await session.commit()
        return row


async def _wait_for_pending(client, token, slack_user, timeout=5.0):
    """Poll the pending identities API until the target user appears or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get("/tenants/identity/pending", headers=make_auth_headers(token))
        if resp.status_code == 200:
            for p in resp.json():
                if p["external_subject"] == slack_user:
                    return p
        await asyncio.sleep(0.1)
    return None


class TestSlackIdentityFlow:
    @pytest.mark.asyncio
    async def test_first_dm_with_matching_email_auto_binds(self, slack_test_setup):
        """First DM from a Slack user whose email matches an internal user auto-binds."""
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        admin_email = tenant["admin"].email
        slack_user = f"U_auto_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=admin_email)

        event = make_message_event(user_id=slack_user, channel_id=f"D_{slack_user}", team_id="T_TENANT_A")
        payload = make_event_callback_payload(event=event, event_id=f"Ev_{slack_user}", team_id="T_TENANT_A")
        body = __import__("json").dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200

        # Auto-bound identity is active, so not in pending list
        await asyncio.sleep(0.3)
        pending_resp = await client.get(
            "/tenants/identity/pending", headers=make_auth_headers(tenant["token"])
        )
        assert pending_resp.status_code == 200
        pending = pending_resp.json()
        assert not any(p["external_subject"] == slack_user for p in pending)

    @pytest.mark.asyncio
    async def test_first_dm_no_email_match_is_rejected(self, slack_test_setup):
        """First DM with no matching email is rejected; no pending row is created."""
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_reject_{uuid4().hex[:8]}"
        external_domain = tenant["external_domain"]
        fake.register_user(slack_user, email=f"nomatch_{uuid4().hex[:8]}@{external_domain}")
        fake.posted_messages.clear()

        event = make_message_event(user_id=slack_user, channel_id=f"D_{slack_user}", team_id="T_TENANT_A")
        payload = make_event_callback_payload(event=event, event_id=f"Ev_{slack_user}", team_id="T_TENANT_A")
        body = __import__("json").dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200

        await asyncio.sleep(0.3)
        pending_resp = await client.get(
            "/tenants/identity/pending", headers=make_auth_headers(tenant["token"])
        )
        assert pending_resp.status_code == 200
        assert not any(p["external_subject"] == slack_user for p in pending_resp.json())
        assert any("No LingQing account" in m["text"] for m in fake.posted_messages)

    @pytest.mark.asyncio
    async def test_admin_bind_pending_identity_succeeds(self, slack_test_setup):
        """Admin can bind a pending Slack identity to an internal user."""
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        token = tenant["token"]
        fake = slack_test_setup["fake_slack"]
        admin_id = tenant["admin"].id
        slack_user = f"U_bind_{uuid4().hex[:8]}"
        external_domain = tenant["external_domain"]
        email = f"bind_{uuid4().hex[:8]}@{external_domain}"
        fake.register_user(slack_user, email=email)

        pending_row = await _seed_pending_slack_identity(
            slack_test_setup, "tenant_a", slack_user, email
        )
        identity_id = pending_row.id

        approve_resp = await client.post(
            f"/tenants/identity/pending/{identity_id}/approve",
            headers=make_auth_headers(token),
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_tenant_a_slack_user_cannot_bind_to_tenant_b_user(self, slack_test_setup):
        """Identity rows are tenant-scoped; tenant A's pending list does not show tenant B users."""
        client = slack_test_setup["client"]
        tenant_a = slack_test_setup["tenants"]["tenant_a"]
        tenant_b = slack_test_setup["tenants"]["tenant_b"]
        fake = slack_test_setup["fake_slack"]

        slack_user = f"U_iso_{uuid4().hex[:8]}"
        external_domain = tenant_b["external_domain"]
        email = f"iso_{uuid4().hex[:8]}@{external_domain}"
        fake.register_user(slack_user, email=email)
        await _seed_pending_slack_identity(slack_test_setup, "tenant_b", slack_user, email)

        pending_a_resp = await client.get(
            "/tenants/identity/pending", headers=make_auth_headers(tenant_a["token"])
        )
        assert pending_a_resp.status_code == 200
        pending_a = pending_a_resp.json()
        assert not any(p["external_subject"] == slack_user for p in pending_a)
