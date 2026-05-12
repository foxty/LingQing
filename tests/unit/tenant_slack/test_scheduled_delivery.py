"""Unit tests for Slack scheduled task delivery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.agent_ingress.slack.scheduled_delivery import (
    SLACK_SCHEDULED_FAILURE_MESSAGE,
    deliver_scheduled_agent_run_to_slack,
    slack_delivery_thread_ts,
)


def test_slack_delivery_thread_ts_empty_returns_none():
    assert slack_delivery_thread_ts("") is None


def test_slack_delivery_thread_ts_returns_value():
    assert slack_delivery_thread_ts("1700000000.000100") == "1700000000.000100"


@pytest.mark.asyncio
async def test_deliver_scheduled_agent_run_no_origin_thread_id():
    result = await deliver_scheduled_agent_run_to_slack(
        tenant_id=1,
        user_id=2,
        origin_thread_id=None,
        response_text="Done",
        db_session=MagicMock(),
    )
    assert result is False


@pytest.mark.asyncio
async def test_deliver_scheduled_agent_run_no_mapping(monkeypatch):
    repo = SimpleNamespace(
        get_thread_link_by_chat_thread_id=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.scheduled_delivery.SlackRepository",
        lambda db: repo,
    )

    result = await deliver_scheduled_agent_run_to_slack(
        tenant_id=1,
        user_id=2,
        origin_thread_id="thread_abc",
        response_text="Done",
        db_session=MagicMock(),
    )

    assert result is False
    repo.get_thread_link_by_chat_thread_id.assert_awaited_once_with(1, "thread_abc")


@pytest.mark.asyncio
async def test_deliver_scheduled_agent_run_endpoint_disabled(monkeypatch):
    link = SimpleNamespace(
        external_channel_id="C123",
        external_thread_key="1700000000.000100",
        endpoint_id=99,
    )
    repo = SimpleNamespace(
        get_thread_link_by_chat_thread_id=AsyncMock(return_value=link),
        decrypt_bot_token=MagicMock(return_value="xoxb-test"),
    )
    db_session = MagicMock()
    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(enabled=False)))
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.scheduled_delivery.SlackRepository",
        lambda db: repo,
    )

    result = await deliver_scheduled_agent_run_to_slack(
        tenant_id=1,
        user_id=2,
        origin_thread_id="thread_abc",
        response_text="Done",
        db_session=db_session,
    )

    assert result is False


@pytest.mark.asyncio
async def test_deliver_scheduled_agent_run_posts_to_thread(monkeypatch):
    link = SimpleNamespace(
        external_channel_id="C123",
        external_thread_key="1700000000.000100",
        endpoint_id=99,
    )
    endpoint = SimpleNamespace(enabled=True)
    repo = SimpleNamespace(
        get_thread_link_by_chat_thread_id=AsyncMock(return_value=link),
        decrypt_bot_token=MagicMock(return_value="xoxb-test"),
    )
    db_session = MagicMock()
    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=endpoint))
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.scheduled_delivery.SlackRepository",
        lambda db: repo,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.scheduled_delivery.get_settings",
        lambda: SimpleNamespace(PORTAL_ORIGIN="https://portal.test", TENANT_APP_API_ORIGIN="https://api.test"),
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.scheduled_delivery.format_reply_for_slack",
        lambda text, **kwargs: text,
    )

    client = SimpleNamespace(chat_post_message=AsyncMock(return_value={"ok": True}))

    result = await deliver_scheduled_agent_run_to_slack(
        tenant_id=1,
        user_id=2,
        origin_thread_id="thread_abc",
        response_text="Summary complete.",
        db_session=db_session,
        client=client,
    )

    assert result is True
    client.chat_post_message.assert_awaited_once_with(
        bot_token="xoxb-test",
        channel="C123",
        text="Summary complete.",
        thread_ts="1700000000.000100",
    )


def test_slack_scheduled_failure_message_matches_ingress_copy():
    assert SLACK_SCHEDULED_FAILURE_MESSAGE == "Sorry, I couldn't process that request. Please try again."
