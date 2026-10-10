"""Integration tests locking Slack first-login bind policies."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from tests.integration.conftest import make_auth_headers
from tests.integration.helpers.ingress_helpers import (
    post_slack_dm,
    set_workspace_bind_policy,
    wait_until_background,
)


class TestSlackBindPolicies:
    @pytest.mark.asyncio
    async def test_attach_policy_auto_binds_matching_email(self, slack_test_setup):
        tenant = slack_test_setup["tenants"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_attach_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)

        result = await post_slack_dm(slack_test_setup, slack_user=slack_user)
        assert result["response"].status_code == 200

        pending_resp = await slack_test_setup["client"].get(
            "/tenants/identity/pending",
            headers=make_auth_headers(tenant["token"]),
        )
        assert not any(p["external_subject"] == slack_user for p in pending_resp.json())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bind_policy", ["jit_create", "pending_approval", "reject_unknown"])
    async def test_first_login_policy_outcomes(self, slack_test_setup, bind_policy, monkeypatch):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        token = tenant["token"]
        team_id = "T_TENANT_A"
        slack_user = f"U_policy_{bind_policy}_{uuid4().hex[:8]}"
        email = f"policy_{uuid4().hex[:8]}@{tenant['external_domain']}"
        fake.register_user(slack_user, email=email)
        fake.posted_messages.clear()

        await set_workspace_bind_policy(
            slack_test_setup["session_factory"],
            tenant_id=tenant["tenant"].id,
            team_id=team_id,
            bind_policy=bind_policy,
        )

        captured: dict[str, object] = {}
        if bind_policy == "jit_create":

            async def fake_chat(self, request, **kwargs):
                captured["called"] = True
                return MagicMock(response=MagicMock(content="ok"))

            monkeypatch.setattr(
                "apps.tenant_app_service.agent_ingress.slack.ingress_service.ChatService.chat",
                fake_chat,
            )

        await post_slack_dm(slack_test_setup, slack_user=slack_user, team_id=team_id)

        pending_resp = await client.get("/tenants/identity/pending", headers=make_auth_headers(token))
        pending = [p for p in pending_resp.json() if p["external_subject"] == slack_user]

        if bind_policy == "jit_create":
            assert not captured.get("called")
            assert not pending
            assert not fake.posted_messages
        elif bind_policy == "pending_approval":
            assert len(pending) == 1
            assert any("pending admin approval" in m["text"] for m in fake.posted_messages)
        else:
            assert not pending
            assert any("No LingQing account" in m["text"] for m in fake.posted_messages)

    @pytest.mark.asyncio
    async def test_domain_not_allowed_rejects_user(self, slack_test_setup):
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_domain_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=f"blocked_{uuid4().hex[:8]}@not-allowed.example")
        fake.posted_messages.clear()

        await post_slack_dm(slack_test_setup, slack_user=slack_user, wait_seconds=0)

        async def _assert_domain_rejection() -> None:
            assert any(
                "email domain is not allowed" in m["text"] for m in fake.posted_messages
            )

        await wait_until_background(_assert_domain_rejection())

    @pytest.mark.asyncio
    async def test_missing_email_rejects_user(self, slack_test_setup):
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_noemail_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=None)
        fake.posted_messages.clear()

        await post_slack_dm(slack_test_setup, slack_user=slack_user, wait_seconds=0)

        async def _assert_missing_email_rejection() -> None:
            assert any(
                "email domain is not allowed" in m["text"]
                or "could not read an email" in m["text"].lower()
                for m in fake.posted_messages
            )

        await wait_until_background(_assert_missing_email_rejection())
