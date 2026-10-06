"""Integration tests for Slack interactivity (feedback buttons)."""

import json
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from sqlalchemy import select

from apps.shared.db.models import ChatMessage, ChatThread, MessageFeedback
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import ACTION_FEEDBACK_POSITIVE
from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository
from tests.slack.fake_slack import make_slack_signature_headers


def _interactivity_body(payload: dict) -> str:
    return urlencode({"payload": json.dumps(payload)})


async def _seed_feedback_context(slack_test_setup, *, message_id: str, slack_user: str) -> None:
    tenant = slack_test_setup["tenants"]["tenant_a"]
    team_id = "T_TENANT_A"
    thread_id = f"thread_feedback_{uuid4().hex[:8]}"

    async with slack_test_setup["session_factory"]() as session:
        thread = ChatThread(
            id=thread_id,
            tenant_id=tenant["tenant"].id,
            user_id=tenant["admin"].id,
            agent_id=-1,
            title="feedback interactivity test",
            message_count=2,
        )
        session.add(thread)
        await session.flush()

        session.add(
            ChatMessage(
                message_id=f"{thread_id}-human",
                thread_id=thread_id,
                type="human",
                content="What is the status?",
                session_id="session_a",
                agent_id=-1,
            )
        )
        session.add(
            ChatMessage(
                message_id=message_id,
                thread_id=thread_id,
                type="ai",
                content="All systems operational.",
                session_id="session_a",
                agent_id=-1,
            )
        )

        source_repo = SlackIdentitySourceRepository(session)
        identity_repo = ExternalIdentityRepository(session)
        source = await source_repo.ensure_slack_workspace_source(
            tenant_id=tenant["tenant"].id,
            team_id=team_id,
        )
        await identity_repo.create_identity(
            tenant_id=tenant["tenant"].id,
            identity_source_id=source.id,
            external_subject=slack_user,
            user_id=tenant["admin"].id,
            email=tenant["admin"].email,
            display_name=slack_user,
            status="active",
        )
        await session.commit()


class TestSlackInteractivity:
    @pytest.mark.asyncio
    async def test_positive_feedback_button_persists_rating(self, slack_test_setup):
        client = slack_test_setup["client"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        endpoint_key = slack_test_setup["endpoint_keys"]["tenant_a"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]

        slack_user = f"U_feedback_{uuid4().hex[:8]}"
        message_id = f"msg_feedback_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)
        await _seed_feedback_context(slack_test_setup, message_id=message_id, slack_user=slack_user)

        channel_id = f"C_feedback_{uuid4().hex[:8]}"
        message_ts = "1234567890.000100"
        payload = {
            "type": "block_actions",
            "user": {"id": slack_user},
            "actions": [{"action_id": ACTION_FEEDBACK_POSITIVE, "value": message_id}],
            "channel": {"id": channel_id},
            "message": {
                "ts": message_ts,
                "text": "All systems operational.",
                "blocks": [{"type": "section", "text": {"text": "All systems operational."}}],
            },
        }
        body = _interactivity_body(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        resp = await client.post(
            f"/ingress/{endpoint_key}/interactions",
            content=body,
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json() == {}

        assert len(fake.updated_messages) == 1
        update = fake.updated_messages[0]
        assert update["channel"] == channel_id
        assert update["ts"] == message_ts
        positive_btn = update["blocks"][1]["elements"][0]
        assert positive_btn["style"] == "primary"
        assert "selected" in positive_btn["text"]["text"].lower()

        async with slack_test_setup["session_factory"]() as session:
            result = await session.execute(
                select(MessageFeedback).where(
                    MessageFeedback.tenant_id == tenant["tenant"].id,
                    MessageFeedback.message_id == message_id,
                    MessageFeedback.user_id == tenant["admin"].id,
                )
            )
            row = result.scalar_one_or_none()
            assert row is not None
            assert row.rating == "positive"
            assert row.source == "slack"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, slack_test_setup):
        client = slack_test_setup["client"]
        endpoint_key = slack_test_setup["endpoint_keys"]["tenant_a"]
        body = _interactivity_body({"type": "block_actions", "actions": []})

        resp = await client.post(
            f"/ingress/{endpoint_key}/interactions",
            content=body,
            headers={
                "X-Slack-Signature": "v0=invalid",
                "X-Slack-Request-Timestamp": "1700000000",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        assert resp.status_code == 401
