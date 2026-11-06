"""Slack Block Kit Stop → cancel_agent_run and update thinking message."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.agent_ingress.slack.interactivity_service import SlackInteractivityService
from apps.tenant_app_service.agent_ingress.slack.messages import SlackMessageKey, slack_user_message


def _stop_payload() -> dict:
    return {
        "type": "block_actions",
        "user": {"id": "U1"},
        "channel": {"id": "C1"},
        "message": {
            "ts": "1.0",
            "text": "🤔 …",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "🤔 …"}}],
        },
        "actions": [{"action_id": "agent_run_stop", "value": "run-99"}],
    }


@pytest.mark.asyncio
async def test_block_action_stop_acks_and_schedules_background_task():
    service = SlackInteractivityService(db=MagicMock())
    endpoint = MagicMock()
    endpoint.id = 7
    endpoint.tenant_id = 2

    def _consume_create_task(coro):
        coro.close()
        return MagicMock()

    with patch(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.asyncio.create_task",
        side_effect=_consume_create_task,
    ) as create_task:
        body = await service.handle_payload(_stop_payload(), endpoint)

    assert body == {}
    create_task.assert_called_once()


@pytest.mark.asyncio
async def test_execute_agent_run_stop_updates_thinking_message_on_success():
    db = MagicMock()
    service = SlackInteractivityService(db=db)
    service.repo = MagicMock()
    service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
    service.client = MagicMock()
    service.client.chat_update = AsyncMock()
    service.identity_service = MagicMock()

    endpoint = MagicMock()
    endpoint.tenant_id = 2

    with (
        patch(
            "apps.tenant_app_service.agent_ingress.slack.interactivity_service.resolve_eligible_slack_user_id",
            new=AsyncMock(return_value=4),
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.interactivity_service.cancel_slack_thread_run_by_run_id",
            new=AsyncMock(),
        ) as cancel_by_run,
    ):
        await service.execute_agent_run_stop(_stop_payload(), endpoint, "run-99")

    cancel_by_run.assert_awaited_once_with(db, tenant_id=2, user_id=4, run_id="run-99")
    service.client.chat_update.assert_awaited_once()
    kwargs = service.client.chat_update.await_args.kwargs
    assert kwargs["channel"] == "C1"
    assert kwargs["ts"] == "1.0"
    assert kwargs["text"] == slack_user_message(SlackMessageKey.REQUEST_CANCELED)
    blocks = kwargs["blocks"]
    assert all(b.get("type") != "actions" for b in blocks)


@pytest.mark.asyncio
async def test_execute_agent_run_stop_already_finished_updates_thinking_message():
    db = MagicMock()
    service = SlackInteractivityService(db=db)
    service.repo = MagicMock()
    service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
    service.client = MagicMock()
    service.client.chat_update = AsyncMock()
    service.identity_service = MagicMock()

    endpoint = MagicMock()
    endpoint.tenant_id = 2

    from apps.shared.core.exceptions import ValidationError

    with (
        patch(
            "apps.tenant_app_service.agent_ingress.slack.interactivity_service.resolve_eligible_slack_user_id",
            new=AsyncMock(return_value=4),
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.interactivity_service.cancel_slack_thread_run_by_run_id",
            new=AsyncMock(
                side_effect=ValidationError(
                    "Agent run already finished",
                    details={"code": "RUN_ALREADY_FINISHED", "status": "completed", "run_id": "run-99"},
                )
            ),
        ),
    ):
        await service.execute_agent_run_stop(_stop_payload(), endpoint, "run-99")

    service.client.chat_update.assert_awaited_once()
    assert service.client.chat_update.await_args.kwargs["text"] == slack_user_message(
        SlackMessageKey.REQUEST_ALREADY_FINISHED
    )
