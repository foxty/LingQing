"""Slack Block Kit Stop → cancel_agent_run only (ingress owns message updates)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.agent_ingress.slack.interactivity_service import SlackInteractivityService


@pytest.mark.asyncio
async def test_block_action_stop_acks_without_updating_message():
    service = SlackInteractivityService(db=MagicMock())
    endpoint = MagicMock()
    endpoint.id = 7
    endpoint.tenant_id = 2

    payload = {
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

    def _consume_create_task(coro):
        coro.close()
        return MagicMock()

    with patch(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.asyncio.create_task",
        side_effect=_consume_create_task,
    ) as create_task:
        body = await service.handle_payload(payload, endpoint)

    assert body == {}
    create_task.assert_called_once()


@pytest.mark.asyncio
async def test_execute_agent_run_stop_cancels_without_chat_update():
    db = MagicMock()
    service = SlackInteractivityService(db=db)
    service.repo = MagicMock()
    service.client = MagicMock()
    service.client.chat_update = AsyncMock()
    service.identity_service = MagicMock()

    endpoint = MagicMock()
    endpoint.tenant_id = 2

    payload = {
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
        await service.execute_agent_run_stop(payload, endpoint, "run-99")

    cancel_by_run.assert_awaited_once_with(db, tenant_id=2, user_id=4, run_id="run-99")
    service.client.chat_update.assert_not_called()


@pytest.mark.asyncio
async def test_execute_agent_run_stop_already_finished_no_chat_update():
    db = MagicMock()
    service = SlackInteractivityService(db=db)
    service.repo = MagicMock()
    service.client = MagicMock()
    service.client.chat_update = AsyncMock()
    service.identity_service = MagicMock()

    endpoint = MagicMock()
    endpoint.tenant_id = 2

    payload = {
        "type": "block_actions",
        "user": {"id": "U1"},
        "channel": {"id": "C1"},
        "message": {"ts": "1.0", "text": "🤔 …", "blocks": []},
        "actions": [{"action_id": "agent_run_stop", "value": "run-99"}],
    }

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
        await service.execute_agent_run_stop(payload, endpoint, "run-99")

    service.client.chat_update.assert_not_called()
