"""Integration tests for Slack Stop (run cancel + ingress delivery guard)."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode
from uuid import uuid4

import pytest

from apps.shared.db.models import ChatThread
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.tenant_app_service.agent_ingress.slack import chat_turn_runner as chat_turn_runner_module
from apps.tenant_app_service.agent_ingress.slack.domain import SlackMessageEvent
from apps.tenant_app_service.agent_ingress.slack.ingress_service import SlackIngressService
from apps.tenant_app_service.agent_ingress.slack.interactivity_service import SlackInteractivityService
from apps.tenant_app_service.agent_ingress.slack.messages import SlackMessageKey, slack_user_message
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.agent_ingress.slack.run_control_blocks import ACTION_AGENT_RUN_STOP
from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository
from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.domain import AgentRunStatus
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.agent_ingress.slack.chat_turn_flow import (
    PostThinkingFn,
    SlackCommittedChatTurnResult,
)
from tests.integration.test_slack_channel_webhook import _wait_for_slack_side_effect
from tests.slack.chat_turn_mock import default_prepared_chat_stream
from tests.slack.fake_slack import make_slack_signature_headers


def _interactivity_body(payload: dict) -> str:
    return urlencode({"payload": json.dumps(payload)})


def _stop_payload(*, run_id: str, slack_user_id: str, channel_id: str = "C1", message_ts: str = "1.0") -> dict:
    return {
        "type": "block_actions",
        "user": {"id": slack_user_id},
        "channel": {"id": channel_id},
        "message": {
            "ts": message_ts,
            "text": "🤔 …",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "🤔 …"}}],
        },
        "actions": [{"action_id": ACTION_AGENT_RUN_STOP, "value": run_id}],
    }


async def _seed_slack_user_for_admin(session, slack_test_setup, *, slack_user_id: str) -> None:
    tenant = slack_test_setup["tenants"]["tenant_a"]
    team_id = "T_TENANT_A"
    source_repo = SlackIdentitySourceRepository(session)
    identity_repo = ExternalIdentityRepository(session)
    source = await source_repo.ensure_slack_workspace_source(
        tenant_id=tenant["tenant"].id,
        team_id=team_id,
    )
    await identity_repo.create_identity(
        tenant_id=tenant["tenant"].id,
        identity_source_id=source.id,
        external_subject=slack_user_id,
        user_id=tenant["admin"].id,
        email=tenant["admin"].email,
        display_name=slack_user_id,
        status="active",
    )


async def _seed_running_run_on_thread(session, slack_test_setup) -> tuple[str, str]:
    """Return (thread_id, run_id) for tenant_a admin."""
    tenant = slack_test_setup["tenants"]["tenant_a"]
    thread_id = f"slack_stop_{uuid4().hex[:12]}"
    session.add(
        ChatThread(
            id=thread_id,
            tenant_id=tenant["tenant"].id,
            user_id=tenant["admin"].id,
            agent_id=-1,
            title="slack stop test",
            message_count=0,
        )
    )
    await session.flush()
    run = await AgentRunRepository(session).create_run(
        tenant_id=tenant["tenant"].id,
        thread_id=thread_id,
        agent_id=-1,
        trigger_message_id=str(uuid4()),
        invoke_index=0,
        session_id=str(uuid4()),
        status=AgentRunStatus.RUNNING,
    )
    await session.commit()
    return thread_id, run.id


@pytest.fixture
def await_interactivity_background_tasks(monkeypatch):
    """Collect Slack stop background tasks so tests can await them after HTTP ack."""
    pending: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def _create_task(coro):
        task = real_create_task(coro)
        pending.append(task)
        return task

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.interactivity_service.asyncio.create_task",
        _create_task,
    )
    return pending


class TestSlackRunStop:
    @pytest.mark.asyncio
    async def test_stop_interaction_cancels_run_and_updates_thinking_message(
        self, slack_test_setup, await_interactivity_background_tasks
    ):
        client = slack_test_setup["client"]
        fake = slack_test_setup["fake_slack"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        endpoint_key = slack_test_setup["endpoint_keys"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        slack_user = f"U_stop_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)

        async with slack_test_setup["session_factory"]() as session:
            await _seed_slack_user_for_admin(session, slack_test_setup, slack_user_id=slack_user)
            _thread_id, run_id = await _seed_running_run_on_thread(session, slack_test_setup)

        fake.updated_messages.clear()
        body = _interactivity_body(_stop_payload(run_id=run_id, slack_user_id=slack_user))
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(f"/ingress/{endpoint_key}/interactions", content=body, headers=headers)
        assert resp.status_code == 200
        if await_interactivity_background_tasks:
            await asyncio.gather(*await_interactivity_background_tasks)

        async def _assert_slack_and_db() -> None:
            assert fake.updated_messages, "expected thinking message chat.update after Stop"
            update = fake.updated_messages[-1]
            canceled = slack_user_message(SlackMessageKey.REQUEST_CANCELED)
            blocks = update.get("blocks") or []
            section = next(block for block in blocks if block.get("type") == "section")
            assert section["text"]["text"] == canceled
            assert all(block.get("type") != "actions" for block in blocks)
            footer_blocks = [block for block in blocks if block.get("block_id") == "turn_duration"]
            assert len(footer_blocks) == 1
            footer = footer_blocks[0]["elements"][0]["text"]
            assert footer.startswith("Took ")
            assert update["text"] == f"{canceled}\n{footer}"

            async with slack_test_setup["session_factory"]() as session:
                run = await AgentRunRepository(session).get_run(tenant["tenant"].id, run_id)
                assert run is not None
                assert run.status == AgentRunStatus.CANCELLED

        await _wait_for_slack_side_effect(_assert_slack_and_db)

    @pytest.mark.asyncio
    async def test_stop_via_service_cancels_run_in_db(self, slack_test_setup):
        """Direct application call with real Postgres (no HTTP) for cancel persistence."""
        tenant = slack_test_setup["tenants"]["tenant_a"]
        slack_user = f"U_stop_svc_{uuid4().hex[:8]}"
        slack_test_setup["fake_slack"].register_user(slack_user, email=tenant["admin"].email)

        async with slack_test_setup["session_factory"]() as session:
            await _seed_slack_user_for_admin(session, slack_test_setup, slack_user_id=slack_user)
            _thread_id, run_id = await _seed_running_run_on_thread(session, slack_test_setup)
            repo = SlackRepository(session)
            endpoint = await repo.get_endpoint_by_key(slack_test_setup["endpoint_keys"]["tenant_a"])
            assert endpoint is not None
            service = SlackInteractivityService(session)
            await service.execute_agent_run_stop(
                _stop_payload(run_id=run_id, slack_user_id=slack_user),
                endpoint,
                run_id,
            )
            await session.commit()

        async with slack_test_setup["session_factory"]() as session:
            run = await AgentRunRepository(session).get_run(tenant["tenant"].id, run_id)
            assert run is not None
            assert run.status == AgentRunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_ingress_skips_final_delivery_when_run_cancelled(self, slack_test_setup):
        tenant = slack_test_setup["tenants"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_skip_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)
        channel_id = f"C_skip_{uuid4().hex[:8]}"
        root_ts = "1700000000.000700"
        undelivered = "must-not-deliver-to-slack"

        async with slack_test_setup["session_factory"]() as session:
            await _seed_slack_user_for_admin(session, slack_test_setup, slack_user_id=slack_user)
            thread_id, run_id = await _seed_running_run_on_thread(session, slack_test_setup)
            await ThreadRunService(session, tenant["tenant"].id).cancel_agent_run(
                thread_id=thread_id,
                run_id=run_id,
            )
            repo = SlackRepository(session)
            endpoint = await repo.get_endpoint_by_key(slack_test_setup["endpoint_keys"]["tenant_a"])
            assert endpoint is not None
            await repo.create_thread_link(
                tenant_id=tenant["tenant"].id,
                endpoint_id=endpoint.id,
                agent_id=-1,
                external_user_id=slack_user,
                external_channel_id=channel_id,
                chat_thread_id=thread_id,
                external_thread_key=root_ts,
            )
            await session.commit()

        async def _stub_turn(
            _tenant_id: int,
            _chat_request,
            _user_dto,
            _access_token: str,
            *,
            post_thinking_placeholder: PostThinkingFn,
            log_label: str = "Slack chat",
        ) -> SlackCommittedChatTurnResult:
            prepared = default_prepared_chat_stream(run_id=run_id, session_id=str(uuid4()))
            thinking_ts = await post_thinking_placeholder(prepared)
            return SlackCommittedChatTurnResult(
                reply_text=undelivered,
                thinking_ts=thinking_ts,
                run_id=run_id,
                session_id=prepared.session_id,
            )

        chat_turn_runner_module.set_slack_chat_turn_runner(_stub_turn)
        fake.posted_messages.clear()
        fake.updated_messages.clear()

        event = SlackMessageEvent(
            event_id=f"Ev_skip_{uuid4().hex[:8]}",
            team_id="T_TENANT_A",
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> after cancel",
            ts=root_ts,
            channel_type="channel",
            source="app_mention",
            bot_user_id="UBOT",
            thread_ts=None,
        )

        async with slack_test_setup["session_factory"]() as session:
            repo = SlackRepository(session)
            endpoint = await repo.get_endpoint_by_key(slack_test_setup["endpoint_keys"]["tenant_a"])
            assert endpoint is not None
            ingress = SlackIngressService(session)
            await ingress.handle_message(event, endpoint.id)
            await session.commit()

        chat_turn_runner_module.reset_slack_chat_turn_runner()

        async def _assert_no_final_delivery() -> None:
            combined_text = " ".join(
                (m.get("text") or "") for m in fake.posted_messages + fake.updated_messages
            )
            assert undelivered not in combined_text
            assert fake.posted_messages, "thinking placeholder should still post"

        await _wait_for_slack_side_effect(_assert_no_final_delivery)
