"""Unit tests for SlackIngressService thread resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.agent_ingress.slack.domain import SlackMessageEvent
from apps.tenant_app_service.agent_ingress.slack.ingress_service import SlackIngressService


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
            "apps.tenant_app_service.chat.thread_service.ThreadService.get_thread",
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
        "apps.tenant_app_service.chat.thread_service.ThreadService.get_thread",
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
            "apps.tenant_app_service.chat.thread_service.ThreadService.get_thread",
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
async def test_handle_message_commits_thread_before_chat_turn():
    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.tenant_id = 2
    endpoint.enabled = True
    endpoint.agent_id = 1

    db = MagicMock()
    db.commit = AsyncMock()

    service = SlackIngressService(db=db)
    service.repo = MagicMock()
    service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
    service.client = MagicMock()
    service.client.chat_post_message = AsyncMock(return_value={"ts": "1.0"})
    service.client.chat_post_ephemeral = AsyncMock()
    service.identity_service = MagicMock()
    bind_result = MagicMock()
    bind_result.action = "allow"
    bind_result.user_id = 4
    bind_result.reason = None
    service.identity_service.resolve_slack_user = AsyncMock(return_value=bind_result)
    service.token_issuer = MagicMock()
    service.token_issuer.issue = MagicMock(return_value="token")

    event = _message_event(channel_type="channel", source="app_mention", text="<@UBOT> hi")

    with (
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.is_eligible_slack_identity",
            return_value=True,
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.user_has_chat_access",
            new=AsyncMock(return_value=True),
        ),
        patch.object(service, "_get_endpoint", new=AsyncMock(return_value=endpoint)),
        patch.object(
            service,
            "_resolve_thread_id",
            new=AsyncMock(return_value=("2_4_1_new", 1)),
        ),
        patch.object(service, "_build_user_dto", new=AsyncMock(return_value=(MagicMock(id=4, role="admin"), "T"))),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.run_slack_chat_turn",
            new=AsyncMock(
                return_value=MagicMock(
                    message_id="m1",
                    session_id="s1",
                    thinking_ts=None,
                    reply_text="ok",
                )
            ),
        ) as run_turn,
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.post_slack_reply_with_feedback",
            new=AsyncMock(),
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.resolve_feedback_message_id",
            new=AsyncMock(return_value="m1"),
        ),
    ):
        await service.handle_message(event, endpoint_id=1)

    db.commit.assert_awaited_once()
    run_turn.assert_awaited_once()


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
            "apps.tenant_app_service.chat.thread_service.ThreadService.get_thread",
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
