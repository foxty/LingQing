"""Integration tests for Slack ingress failure paths and post-approve chat."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from tests.integration.conftest import make_auth_headers
from tests.integration.helpers.ingress_helpers import (
    post_slack_dm,
    seed_pending_slack_identity,
    wait_until_background,
)
from tests.integration.test_slack_config_api import _create_test_agent


class TestSlackIngressFailures:
    @pytest.mark.asyncio
    async def test_users_info_failure_posts_retry_message(self, slack_test_setup):
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_noprofile_{uuid4().hex[:8]}"
        fake.posted_messages.clear()
        fake.ephemeral_messages.clear()

        await post_slack_dm(slack_test_setup, slack_user=slack_user)

        assert any(
            "Could not reach Slack to verify your account" in m["text"]
            for m in fake.ephemeral_messages
        )

    @pytest.mark.asyncio
    async def test_auth_test_failure_on_create_integration(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        fake = slack_test_setup["fake_slack"]
        agent_id = await _create_test_agent(client, token)

        fake.default_auth_ok = False
        resp = await client.post(
            f"/agents/{agent_id}/integrations/slack",
            json={
                "bot_token": "xoxb-invalid",
                "signing_secret": "secret",
                "enabled": True,
            },
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "SLACK_INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_approve_pending_allows_second_dm_chat(self, slack_test_setup, monkeypatch):
        tenant = slack_test_setup["tenants"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        token = tenant["token"]
        slack_user = f"U_approve_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)

        row = await seed_pending_slack_identity(
            slack_test_setup["session_factory"],
            tenant_id=tenant["tenant"].id,
            team_id="T_TENANT_A",
            slack_user=slack_user,
            email=tenant["admin"].email,
        )

        approve_resp = await slack_test_setup["client"].post(
            f"/tenants/identity/pending/{row.id}/approve",
            headers=make_auth_headers(token),
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "active"

        captured: dict[str, object] = {}

        from tests.slack.chat_turn_mock import patch_slack_chat_turn

        def on_complete(_self, _request, _user, _prepared, **_kwargs):
            captured["called"] = True
            return MagicMock(response=MagicMock(content="welcome back"))

        patch_slack_chat_turn(on_complete=on_complete)

        fake.posted_messages.clear()
        await post_slack_dm(slack_test_setup, slack_user=slack_user, wait_seconds=0)

        async def _assert_chat_invoked() -> None:
            assert captured.get("called") is True

        await wait_until_background(_assert_chat_invoked)

    @pytest.mark.asyncio
    async def test_seeded_pending_can_be_rejected(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        token = tenant["token"]
        slack_user = f"U_reject_{uuid4().hex[:8]}"
        email = f"reject_{uuid4().hex[:8]}@{tenant['external_domain']}"

        row = await seed_pending_slack_identity(
            slack_test_setup["session_factory"],
            tenant_id=tenant["tenant"].id,
            team_id="T_TENANT_A",
            slack_user=slack_user,
            email=email,
        )

        reject_resp = await client.post(
            f"/tenants/identity/pending/{row.id}/reject",
            headers=make_auth_headers(token),
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"
