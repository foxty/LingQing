"""Integration tests for Slack tenant isolation boundaries.

Verifies that conversation mappings, external identities, and webhook
configs are isolated by tenant_id and cannot cross tenants.
"""

import asyncio
import json

import pytest

from tests.integration.conftest import make_auth_headers
from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import make_event_callback_payload, make_message_event


class TestSlackTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_a_webhook_cannot_process_tenant_b_team_id(self, slack_test_setup):
        """An event signed with tenant A's secret but carrying tenant B's team_id is rejected."""
        client = slack_test_setup["client"]
        tenant_a = slack_test_setup["tenants"]["tenant_a"]
        signing_secret_a = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        fake.register_user("U_iso_1", email=tenant_a["admin"].email)

        # tenant A is configured with team_id T_TENANT_A; send an event with T_TENANT_B
        event = make_message_event(user_id="U_iso_1", channel_id="D_iso_1", team_id="T_TENANT_B")
        payload = make_event_callback_payload(event=event, event_id="Ev_iso_1", team_id="T_TENANT_B")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret_a, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_conversation_mappings_isolated_by_tenant(self, slack_test_setup):
        """Conversation mappings are scoped by tenant_id and cannot cross."""
        client = slack_test_setup["client"]
        tenant_a = slack_test_setup["tenants"]["tenant_a"]
        tenant_b = slack_test_setup["tenants"]["tenant_b"]
        signing_secret_a = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        fake.register_user("U_map", email=tenant_a["admin"].email)

        # Create a mapping in tenant A
        event = make_message_event(user_id="U_map", channel_id="D_map", team_id="T_TENANT_A")
        payload = make_event_callback_payload(event=event, event_id="Ev_map", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret_a, body=body)
        await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        await asyncio.sleep(0.3)

        # Tenant B's pending list should not contain tenant A's user
        pending_b_resp = await client.get(
            "/tenants/identity/pending", headers=make_auth_headers(tenant_b["token"])
        )
        assert pending_b_resp.status_code == 200
        pending_b = pending_b_resp.json()
        assert not any(p["external_subject"] == "U_map" for p in pending_b)
