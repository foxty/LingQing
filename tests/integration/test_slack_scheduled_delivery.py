"""Integration tests for scheduled agent_run Slack thread delivery."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from apps.shared.tasks.domain import ScheduledTaskDomain
from apps.tenant_app_service.chat.schemas import ChatResponse, Message
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.agent_ingress.slack.scheduled_delivery import (
    SLACK_SCHEDULED_FAILURE_MESSAGE,
    deliver_scheduled_agent_run_to_slack,
)
from apps.tenant_app_service.tasks.agent_run_executor import execute_agent_run_task


def _scheduled_task(**task_config) -> ScheduledTaskDomain:
    now = datetime.now(timezone.utc)
    return ScheduledTaskDomain(
        id=1,
        tenant_id=task_config.pop("_tenant_id", 0),
        user_id=task_config.pop("_user_id", 0),
        name="scheduled slack task",
        task_type="agent_run",
        task_config=task_config,
        schedule_type="once",
        schedule_spec={},
        status="running",
        next_run_at=None,
        last_run_at=None,
        notification_channels=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_repository_get_conversation_mapping_by_thread_id_roundtrip(
    slack_test_setup,
    pg_async_db_session,
):
    tenant = slack_test_setup["tenants"]["tenant_a"]
    tenant_id = tenant["tenant"].id
    thread_id = f"thread_repo_{uuid4().hex[:8]}"
    channel_id = f"C_{uuid4().hex[:8]}"
    thread_ts = "1700000000.000100"
    slack_user = f"U_{uuid4().hex[:8]}"

    repo = SlackRepository(pg_async_db_session)
    endpoint = await repo.get_endpoint(tenant_id)
    assert endpoint is not None
    created = await repo.create_thread_link(
        tenant_id=tenant_id,
        endpoint_id=endpoint.id,
        agent_id=endpoint.agent_id,
        external_user_id=slack_user,
        external_channel_id=channel_id,
        chat_thread_id=thread_id,
        external_thread_key=thread_ts,
    )
    await pg_async_db_session.commit()

    found = await repo.get_thread_link_by_chat_thread_id(tenant_id, thread_id)

    assert found is not None
    assert found.id == created.id
    assert found.external_channel_id == channel_id
    assert found.external_thread_key == thread_ts


@pytest.mark.asyncio
async def test_deliver_scheduled_agent_run_posts_to_mapped_slack_thread(
    slack_test_setup,
    pg_async_db_session,
):
    tenant = slack_test_setup["tenants"]["tenant_a"]
    fake = slack_test_setup["fake_slack"]
    tenant_id = tenant["tenant"].id
    user_id = tenant["admin"].id
    thread_id = f"thread_delivery_{uuid4().hex[:8]}"
    channel_id = f"C_{uuid4().hex[:8]}"
    thread_ts = "1700000001.000200"
    slack_user = f"U_{uuid4().hex[:8]}"
    fake.posted_messages.clear()

    repo = SlackRepository(pg_async_db_session)
    endpoint = await repo.get_endpoint(tenant_id)
    assert endpoint is not None
    await repo.create_thread_link(
        tenant_id=tenant_id,
        endpoint_id=endpoint.id,
        agent_id=endpoint.agent_id,
        external_user_id=slack_user,
        external_channel_id=channel_id,
        chat_thread_id=thread_id,
        external_thread_key=thread_ts,
    )
    await pg_async_db_session.commit()

    delivered = await deliver_scheduled_agent_run_to_slack(
        tenant_id=tenant_id,
        user_id=user_id,
        origin_thread_id=thread_id,
        response_text="Scheduled summary complete.",
        db_session=pg_async_db_session,
    )

    assert delivered is True
    assert len(fake.posted_messages) == 1
    message = fake.posted_messages[0]
    assert message["channel"] == channel_id
    assert message["thread_ts"] == thread_ts
    assert "Scheduled summary complete." in message["text"]


@pytest.mark.asyncio
async def test_execute_agent_run_task_delivers_to_slack_thread(
    slack_test_setup,
    pg_async_db_session,
    monkeypatch,
):
    tenant = slack_test_setup["tenants"]["tenant_a"]
    fake = slack_test_setup["fake_slack"]
    tenant_id = tenant["tenant"].id
    user_id = tenant["admin"].id
    origin_thread_id = f"thread_executor_{uuid4().hex[:8]}"
    channel_id = f"C_{uuid4().hex[:8]}"
    thread_ts = "1700000002.000300"
    slack_user = f"U_{uuid4().hex[:8]}"
    fake.posted_messages.clear()

    repo = SlackRepository(pg_async_db_session)
    endpoint = await repo.get_endpoint(tenant_id)
    assert endpoint is not None
    await repo.create_thread_link(
        tenant_id=tenant_id,
        endpoint_id=endpoint.id,
        agent_id=endpoint.agent_id,
        external_user_id=slack_user,
        external_channel_id=channel_id,
        chat_thread_id=origin_thread_id,
        external_thread_key=thread_ts,
    )
    await pg_async_db_session.commit()

    @asynccontextmanager
    async def fake_app_db_session():
        yield pg_async_db_session

    class FakeChatService:
        def __init__(self, tenant_id_arg, db):
            assert tenant_id_arg == tenant_id

        async def run_headless(self, **kwargs):
            assert kwargs["origin_thread_id"] == origin_thread_id
            return ChatResponse(
                response=Message(
                    role="ai",
                    content="Executor reply for Slack.",
                    agent_id=-1,
                    thread_id=origin_thread_id,
                    session_id="session_exec",
                ),
                agent_id=-1,
                tenant_id=tenant_id,
            )

    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.app_db_session",
        fake_app_db_session,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.ChatService",
        FakeChatService,
    )

    result = await execute_agent_run_task(
        _scheduled_task(
            _tenant_id=tenant_id,
            _user_id=user_id,
            agent_id=-1,
            task_description="Run scheduled summary",
            origin_thread_id=origin_thread_id,
        )
    )

    assert result.success is True
    assert result.payload["slack_thread_delivered"] is True
    assert len(fake.posted_messages) == 1
    assert fake.posted_messages[0]["channel"] == channel_id
    assert fake.posted_messages[0]["thread_ts"] == thread_ts
    assert "Executor reply for Slack." in fake.posted_messages[0]["text"]


@pytest.mark.asyncio
async def test_execute_agent_run_task_failure_delivers_error_to_slack_thread(
    slack_test_setup,
    pg_async_db_session,
    monkeypatch,
):
    tenant = slack_test_setup["tenants"]["tenant_a"]
    fake = slack_test_setup["fake_slack"]
    tenant_id = tenant["tenant"].id
    user_id = tenant["admin"].id
    origin_thread_id = f"thread_failure_{uuid4().hex[:8]}"
    channel_id = f"C_{uuid4().hex[:8]}"
    slack_user = f"U_{uuid4().hex[:8]}"
    fake.posted_messages.clear()

    repo = SlackRepository(pg_async_db_session)
    endpoint = await repo.get_endpoint(tenant_id)
    assert endpoint is not None
    await repo.create_thread_link(
        tenant_id=tenant_id,
        endpoint_id=endpoint.id,
        agent_id=endpoint.agent_id,
        external_user_id=slack_user,
        external_channel_id=channel_id,
        chat_thread_id=origin_thread_id,
        external_thread_key="",
    )
    await pg_async_db_session.commit()

    @asynccontextmanager
    async def fake_app_db_session():
        yield pg_async_db_session

    class FakeChatService:
        def __init__(self, tenant_id_arg, db):
            pass

        async def run_headless(self, **_kwargs):
            raise RuntimeError("chat failed")

    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.app_db_session",
        fake_app_db_session,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.tasks.agent_run_executor.ChatService",
        FakeChatService,
    )

    result = await execute_agent_run_task(
        _scheduled_task(
            _tenant_id=tenant_id,
            _user_id=user_id,
            agent_id=-1,
            task_description="Run scheduled summary",
            origin_thread_id=origin_thread_id,
        )
    )

    assert result.success is False
    assert result.payload["slack_thread_delivered"] is True
    assert len(fake.posted_messages) == 1
    assert fake.posted_messages[0]["text"] == SLACK_SCHEDULED_FAILURE_MESSAGE
    assert fake.posted_messages[0]["thread_ts"] is None
