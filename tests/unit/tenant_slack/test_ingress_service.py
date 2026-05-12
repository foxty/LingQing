"""Unit tests for SlackIngressService thread resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.slack.domain import SlackMessageEvent
from apps.tenant_app_service.slack.ingress_service import SlackIngressService


def _message_event(**kwargs) -> SlackMessageEvent:
    defaults = {
        "event_id": "Ev1",
        "team_id": "T1",
        "user_id": "U1",
        "channel_id": "D123",
        "text": "hi",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "source": "dm",
    }
    defaults.update(kwargs)
    return SlackMessageEvent(**defaults)


@pytest.mark.asyncio
async def test_get_or_create_thread_reuses_link_and_uses_endpoint_agent():
    stale_link = MagicMock()
    stale_link.chat_thread_id = "2_4_-1_existing"
    stale_link.agent_id = -1

    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.agent_id = 1

    repo = MagicMock()
    repo.get_thread_link = AsyncMock(return_value=stale_link)
    repo.create_thread_link = AsyncMock()

    service = SlackIngressService(db=MagicMock())
    service.repo = repo
    existing_thread = MagicMock()
    existing_thread.agent_id = 1

    with (
        patch(
            "apps.tenant_app_service.slack.ingress_service.ChatService.get_thread",
            new=AsyncMock(return_value=existing_thread),
        ),
        patch.object(service, "_create_slack_thread", new=AsyncMock()) as create_thread,
    ):
        thread_id, agent_id = await service._get_or_create_thread(
            tenant_id=2,
            event=_message_event(),
            endpoint=endpoint,
            user_id=4,
            mapping_ts="",
        )

    assert thread_id == "2_4_-1_existing"
    assert agent_id == 1
    create_thread.assert_not_awaited()
    repo.create_thread_link.assert_not_awaited()
    repo.get_thread_link.assert_awaited_once_with(2, "D123", "", endpoint_id=1)


@pytest.mark.asyncio
async def test_thread_reply_uses_endpoint_agent_from_stale_link():
    stale_link = MagicMock()
    stale_link.chat_thread_id = "2_4_-1_existing"
    stale_link.agent_id = -1

    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.agent_id = 1

    repo = MagicMock()
    repo.get_thread_link = AsyncMock(return_value=stale_link)

    service = SlackIngressService(db=MagicMock())
    service.repo = repo
    existing_thread = MagicMock()
    existing_thread.agent_id = 1

    with patch(
        "apps.tenant_app_service.slack.ingress_service.ChatService.get_thread",
        new=AsyncMock(return_value=existing_thread),
    ):
        result = await service._resolve_thread_id(
            tenant_id=2,
            event=_message_event(source="thread_reply"),
            endpoint=endpoint,
            user_id=4,
        )

    assert result == ("2_4_-1_existing", 1)
    repo.get_thread_link.assert_awaited_once_with(2, "D123", "", endpoint_id=1)


@pytest.mark.asyncio
async def test_get_or_create_thread_realigns_when_chat_thread_agent_differs():
    stale_link = MagicMock()
    stale_link.chat_thread_id = "2_4_-1_existing"

    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.agent_id = 1

    stale_thread = MagicMock()
    stale_thread.agent_id = -1
    new_thread = MagicMock()
    new_thread.id = "2_4_1_new"

    repo = MagicMock()
    repo.get_thread_link = AsyncMock(return_value=stale_link)
    repo.update_thread_link = AsyncMock(return_value=stale_link)

    service = SlackIngressService(db=MagicMock())
    service.repo = repo

    with (
        patch(
            "apps.tenant_app_service.slack.ingress_service.ChatService.get_thread",
            new=AsyncMock(return_value=stale_thread),
        ),
        patch.object(service, "_create_slack_thread", new=AsyncMock(return_value=new_thread)) as create_thread,
    ):
        thread_id, agent_id = await service._get_or_create_thread(
            tenant_id=2,
            event=_message_event(),
            endpoint=endpoint,
            user_id=4,
            mapping_ts="",
        )

    assert thread_id == "2_4_1_new"
    assert agent_id == 1
    create_thread.assert_awaited_once()
    repo.update_thread_link.assert_awaited_once_with(
        stale_link,
        chat_thread_id="2_4_1_new",
        agent_id=1,
    )


@pytest.mark.asyncio
async def test_get_or_create_thread_rebinds_when_chat_thread_deleted():
    stale_link = MagicMock()
    stale_link.chat_thread_id = "2_4_1_deleted"

    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.agent_id = 1

    new_thread = MagicMock()
    new_thread.id = "2_4_1_new"

    repo = MagicMock()
    repo.get_thread_link = AsyncMock(return_value=stale_link)
    repo.update_thread_link = AsyncMock(return_value=stale_link)

    service = SlackIngressService(db=MagicMock())
    service.repo = repo

    with (
        patch(
            "apps.tenant_app_service.slack.ingress_service.ChatService.get_thread",
            new=AsyncMock(return_value=None),
        ),
        patch.object(service, "_create_slack_thread", new=AsyncMock(return_value=new_thread)) as create_thread,
    ):
        thread_id, agent_id = await service._get_or_create_thread(
            tenant_id=2,
            event=_message_event(),
            endpoint=endpoint,
            user_id=4,
            mapping_ts="",
        )

    assert thread_id == "2_4_1_new"
    assert agent_id == 1
    create_thread.assert_awaited_once()
    repo.update_thread_link.assert_awaited_once_with(
        stale_link,
        chat_thread_id="2_4_1_new",
        agent_id=1,
    )
