"""Tests for Slack feedback interactivity service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.db.models import AgentIngressEndpoint
from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import (
    ACTION_FEEDBACK_POSITIVE,
)
from apps.tenant_app_service.agent_ingress.slack.interactivity_service import SlackInteractivityService


@pytest.fixture
def endpoint() -> AgentIngressEndpoint:
    row = AgentIngressEndpoint(
        id=1,
        tenant_id=1,
        agent_id=2,
        endpoint_key="ep_test",
        credentials_encrypted={"bot_token": "enc", "signing_secret": "enc"},
        enabled=True,
    )
    return row


@pytest.mark.asyncio
async def test_block_actions_denied_for_ineligible_user(endpoint, monkeypatch):
    db = AsyncMock()
    service = SlackInteractivityService(db)
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.resolve_eligible_slack_user_id",
        AsyncMock(return_value=None),
    )

    result = await service._handle_block_actions(
        {
            "actions": [{"action_id": ACTION_FEEDBACK_POSITIVE, "value": "msg_1"}],
            "user": {"id": "U1"},
        },
        endpoint,
    )

    assert result == {}


@pytest.mark.asyncio
async def test_block_actions_upserts_and_updates_message(endpoint, monkeypatch):
    db = AsyncMock()
    service = SlackInteractivityService(db)
    service.repo = MagicMock()
    service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
    service.client = MagicMock()
    service.client.chat_update = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.resolve_eligible_slack_user_id",
        AsyncMock(return_value=42),
    )

    feedback_service = MagicMock()
    feedback_service.upsert_feedback_for_message_id = AsyncMock()

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.MessageFeedbackService",
        lambda *_args, **_kwargs: feedback_service,
    )
    result = await service._handle_block_actions(
        {
            "actions": [{"action_id": ACTION_FEEDBACK_POSITIVE, "value": "msg_1"}],
            "user": {"id": "U1"},
            "channel": {"id": "C123"},
            "message": {
                "ts": "123.456",
                "text": "Hello",
                "blocks": [{"type": "section", "text": {"text": "Hello"}}],
            },
        },
        endpoint,
    )

    feedback_service.upsert_feedback_for_message_id.assert_awaited_once()
    service.client.chat_update.assert_awaited_once()
    update_kwargs = service.client.chat_update.await_args.kwargs
    assert update_kwargs["channel"] == "C123"
    assert update_kwargs["ts"] == "123.456"
    positive_btn = update_kwargs["blocks"][1]["elements"][0]
    assert positive_btn["style"] == "primary"
    assert result == {}


@pytest.mark.asyncio
async def test_block_actions_preserves_table_and_image(endpoint, monkeypatch):
    db = AsyncMock()
    service = SlackInteractivityService(db)
    service.repo = MagicMock()
    service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
    service.client = MagicMock()
    service.client.chat_update = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.resolve_eligible_slack_user_id",
        AsyncMock(return_value=42),
    )
    feedback_service = MagicMock()
    feedback_service.upsert_feedback_for_message_id = AsyncMock()
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.MessageFeedbackService",
        lambda *_args, **_kwargs: feedback_service,
    )
    table = {"type": "table", "rows": [[{"type": "raw_text", "text": "A"}]]}
    image = {"type": "image", "image_url": "https://cdn.example.com/plot.png", "alt_text": "Plot"}

    await service._handle_block_actions(
        {
            "actions": [{"action_id": ACTION_FEEDBACK_POSITIVE, "value": "msg_1"}],
            "user": {"id": "U1"},
            "channel": {"id": "C123"},
            "message": {
                "ts": "123.456",
                "text": "Intro",
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": "Intro"}},
                    table,
                    image,
                    {"type": "actions", "block_id": "feedback_msg_1", "elements": []},
                ],
            },
        },
        endpoint,
    )

    updated = service.client.chat_update.await_args.kwargs["blocks"]
    assert updated[1] == table
    assert updated[2] == image
    assert updated[3]["type"] == "actions"
    assert updated[3]["elements"][0]["style"] == "primary"
