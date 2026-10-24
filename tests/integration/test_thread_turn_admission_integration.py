"""Integration tests for per-thread chat turn admission (busy gate + advisory lock).

Overlapping in-flight turns are exercised via committed ``POST /chat`` tests below.
Slack busy behavior when a thread is already running uses ``slack_committed_chat_setup``
and seeded session state (not parallel webhooks on the savepoint Slack DB).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.core.exceptions import ThreadBusyError
from apps.shared.db.models import ChatMessage, ChatThread, ThreadMainMessage
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_ingress.slack.messages import SlackMessageKey, slack_user_message
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.turn_service import ChatTurnService
from apps.tenant_app_service.chat.turn_admission import (
    guard_thread_turn_start,
    try_acquire_thread_turn_xact_lock,
)
from apps.tenant_app_service.server import app
from tests.integration.helpers.committed_chat_setup import seed_running_human_turn
from tests.integration.helpers.slow_agent_turn import patch_fast_agent_graph, patch_in_flight_agent_graph
from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import make_app_mention_event, make_event_callback_payload

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_guard_rejects_thread_with_running_human_turn(committed_chat_setup: dict):
    thread_id = committed_chat_setup["thread_id"]
    tenant_id = committed_chat_setup["tenant_id"]
    agent_id = committed_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"

    async with committed_chat_setup["session_local"]() as db:
        await seed_running_human_turn(
            db,
            thread_id=thread_id,
            agent_id=agent_id,
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=committed_chat_setup["owner_id"],
        )

    async with committed_chat_setup["session_local"]() as db:
        with pytest.raises(ThreadBusyError) as exc_info:
            await guard_thread_turn_start(
                db,
                tenant_id=tenant_id,
                thread_id=thread_id,
                agent_id=agent_id,
                skip_busy_check=False,
            )

    assert exc_info.value.details.get("reason") == "thread_status_busy"
    assert exc_info.value.details.get("thread_status") == "running"


@pytest.mark.asyncio
async def test_guard_allows_thread_after_ai_response(committed_chat_setup: dict):
    thread_id = committed_chat_setup["thread_id"]
    tenant_id = committed_chat_setup["tenant_id"]
    agent_id = committed_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"

    async with committed_chat_setup["session_local"]() as db:
        await seed_running_human_turn(
            db,
            thread_id=thread_id,
            agent_id=agent_id,
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=committed_chat_setup["owner_id"],
        )
        from apps.shared.db.models import AgentRunMessage
        from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
        from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository

        run = await AgentRunRepository(db).get_by_session_id(session_id)
        assert run is not None
        db.add(
            AgentRunMessage(
                message_id=f"{thread_id}-ai",
                run_id=run.id,
                thread_id=thread_id,
                type="ai",
                content="done",
                session_id=session_id,
                agent_id=agent_id,
                timestamp=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
        )
        await AgentRunRepository(db).set_status(run.id, status=AgentRunStatus.COMPLETED)
        await db.commit()

    async with committed_chat_setup["session_local"]() as db:
        await guard_thread_turn_start(
            db,
            tenant_id=tenant_id,
            thread_id=thread_id,
            agent_id=agent_id,
            skip_busy_check=False,
        )


@pytest.mark.asyncio
async def test_advisory_xact_lock_blocks_second_connection(committed_chat_setup: dict):
    pg_url = committed_chat_setup["pg_url"]
    tenant_id = committed_chat_setup["tenant_id"]
    thread_id = committed_chat_setup["thread_id"]

    acquired = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock_until_released() -> None:
        engine = create_async_engine(pg_url, future=True, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                async with conn.begin():
                    session = AsyncSession(bind=conn, expire_on_commit=False)
                    await try_acquire_thread_turn_xact_lock(
                        session,
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                    )
                    acquired.set()
                    await release.wait()
        finally:
            await engine.dispose()

    holder = asyncio.create_task(hold_lock_until_released())
    await asyncio.wait_for(acquired.wait(), timeout=10.0)

    engine2 = create_async_engine(pg_url, future=True, poolclass=NullPool)
    try:
        async with engine2.connect() as conn:
            async with conn.begin():
                session = AsyncSession(bind=conn, expire_on_commit=False)
                with pytest.raises(ThreadBusyError) as exc_info:
                    await try_acquire_thread_turn_xact_lock(
                        session,
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                    )
                assert exc_info.value.details.get("reason") == "advisory_lock_not_acquired"
    finally:
        await engine2.dispose()
        release.set()
        await holder


@pytest.mark.asyncio
async def test_prepare_chat_turn_rejects_while_run_in_progress(committed_chat_setup: dict):
    thread_id = committed_chat_setup["thread_id"]
    tenant_id = committed_chat_setup["tenant_id"]
    agent_id = committed_chat_setup["agent_id"]
    session_id = f"sess-busy-{uuid4().hex[:8]}"

    async with committed_chat_setup["session_local"]() as db:
        await seed_running_human_turn(
            db,
            thread_id=thread_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    async with committed_chat_setup["session_local"]() as db:
        before = await db.scalar(
            select(func.count())
            .select_from(ThreadMainMessage)
            .where(ThreadMainMessage.thread_id == thread_id, ThreadMainMessage.type == "human")
        )

    service = ChatTurnService(tenant_id, AsyncMock())
    service._resolve_agent_id = AsyncMock(return_value=agent_id)
    service._cancel_superseded_hitl_if_needed = AsyncMock()
    agent_graph = AsyncMock()
    agent_graph.get_name = lambda: "Agent"
    service._get_agent_graph = AsyncMock(return_value=(agent_graph, None))
    service._convert_to_langchain_messages = lambda messages: messages
    service._inject_message_attachments = AsyncMock(side_effect=lambda lc_messages, **kwargs: lc_messages)
    service.get_tenant_domain = AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {})))
    service._build_runtime_config = MagicMock(
        return_value={"configurable": {"thread_id": thread_id}},
    )
    service.create_thread_title_if_1st_message = AsyncMock(return_value=None)
    service._build_initial_agent_messages = lambda lc_messages, request: lc_messages
    service._is_hitl_continuation = lambda request: False

    request = ChatRequest(
        tenant_id=tenant_id,
        agent_id=agent_id,
        message=SimpleMessage(role="human", content="another message"),
        thread_id=thread_id,
    )
    user = UserDTO(
        id=committed_chat_setup["owner_id"],
        username="owner",
        role="admin",
        tenant_id=tenant_id,
        tenant_name="test",
    )

    async with committed_chat_setup["session_local"]() as db:
        service.db = db
        with pytest.raises(ThreadBusyError):
            await service.prepare_chat_turn(request, user)

    async with committed_chat_setup["session_local"]() as db:
        after = await db.scalar(
            select(func.count())
            .select_from(ThreadMainMessage)
            .where(ThreadMainMessage.thread_id == thread_id, ThreadMainMessage.type == "human")
        )
        assert after == before


@pytest.mark.asyncio
async def test_post_chat_returns_409_thread_busy(committed_chat_setup: dict):
    thread_id = committed_chat_setup["thread_id"]
    tenant_id = committed_chat_setup["tenant_id"]
    agent_id = committed_chat_setup["agent_id"]
    session_id = f"sess-http-{uuid4().hex[:8]}"

    async with committed_chat_setup["session_local"]() as db:
        await seed_running_human_turn(
            db,
            thread_id=thread_id,
            agent_id=agent_id,
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=committed_chat_setup["owner_id"],
        )

    client = TestClient(app)
    response = client.post(
        "/chat",
        headers=committed_chat_setup["owner_headers"],
        json={
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "thread_id": thread_id,
            "message": {"role": "human", "content": "while running"},
        },
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "THREAD_BUSY"
    assert "request_id" in body


@pytest.mark.asyncio
async def test_slack_mention_while_thread_busy_posts_ephemeral_only(
    slack_committed_chat_setup: dict, monkeypatch
):
    session_factory: async_sessionmaker[AsyncSession] = slack_committed_chat_setup["session_factory"]

    complete_called = {"value": False}

    async def _complete_must_not_run(*_args, **_kwargs):
        complete_called["value"] = True
        raise AssertionError("complete_chat_turn_committed must not run when thread is busy")

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.chat_turn_flow.complete_chat_turn_committed",
        _complete_must_not_run,
    )

    client = slack_committed_chat_setup["client"]
    tenant = slack_committed_chat_setup["tenants"]["tenant_a"]
    signing_secret = slack_committed_chat_setup["secrets"]["tenant_a"]
    fake = slack_committed_chat_setup["fake_slack"]
    slack_user = f"U_busy_{uuid4().hex[:8]}"
    channel_id = f"C_busy_{uuid4().hex[:8]}"
    thread_root = "1700000000.002200"
    chat_thread_id = f"thread-slack-busy-{uuid4().hex[:8]}"
    running_session_id = f"sess-{uuid4().hex[:8]}"
    tenant_id = tenant["tenant"].id
    user_id = tenant["admin"].id
    fake.register_user(slack_user, email=tenant["admin"].email)
    fake.posted_messages.clear()
    fake.ephemeral_messages.clear()

    async with session_factory() as db:
        db.add(
            ChatThread(
                id=chat_thread_id,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=-1,
                title="slack busy test",
                message_count=1,
            )
        )
        await db.flush()
        repo = SlackRepository(db)
        endpoint = await repo.get_endpoint(tenant_id)
        assert endpoint is not None
        await repo.create_thread_link(
            tenant_id=tenant_id,
            endpoint_id=endpoint.id,
            agent_id=-1,
            external_user_id=slack_user,
            external_channel_id=channel_id,
            chat_thread_id=chat_thread_id,
            external_thread_key=thread_root,
        )
        await seed_running_human_turn(
            db,
            thread_id=chat_thread_id,
            agent_id=-1,
            session_id=running_session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    async with session_factory() as db:
        human_count_before = await db.scalar(
            select(func.count())
            .select_from(ThreadMainMessage)
            .where(
                ThreadMainMessage.thread_id == chat_thread_id,
                ThreadMainMessage.type == "human",
            )
        )
    assert human_count_before == 1

    event = make_app_mention_event(
        user_id=slack_user,
        channel_id=channel_id,
        text="<@UBOT> while busy",
        team_id="T_TENANT_A",
        ts=thread_root,
    )
    body = json.dumps(
        make_event_callback_payload(
            event=event,
            event_id=f"Ev_busy_{uuid4().hex[:8]}",
            team_id="T_TENANT_A",
        )
    )
    headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
    url = f"/ingress/{slack_committed_chat_setup['endpoint_keys']['tenant_a']}/events"

    resp = await client.post(url, content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    expected = slack_user_message(SlackMessageKey.THREAD_BUSY)
    deadline = asyncio.get_event_loop().time() + 8.0
    while asyncio.get_event_loop().time() < deadline:
        if any(expected in m["text"] for m in fake.ephemeral_messages):
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("expected THREAD_BUSY ephemeral")

    assert not fake.posted_messages
    assert not fake.updated_messages
    assert complete_called["value"] is False

    async with session_factory() as db:
        human_count_after = await db.scalar(
            select(func.count())
            .select_from(ThreadMainMessage)
            .where(
                ThreadMainMessage.thread_id == chat_thread_id,
                ThreadMainMessage.type == "human",
            )
        )
    assert human_count_after == human_count_before


def _chat_post_body(committed_chat_setup: dict, *, content: str) -> dict:
    return {
        "tenant_id": committed_chat_setup["tenant_id"],
        "agent_id": committed_chat_setup["agent_id"],
        "thread_id": committed_chat_setup["thread_id"],
        "message": {"role": "human", "content": content},
    }


@pytest.mark.asyncio
async def test_overlapping_post_chat_rejects_second_while_first_in_flight(
    committed_chat_setup: dict, monkeypatch
):
    import httpx

    from apps.tenant_app_service.server import app

    in_flight = asyncio.Event()
    release = asyncio.Event()
    patch_in_flight_agent_graph(monkeypatch, in_flight=in_flight, release=release)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first_task = asyncio.create_task(
            client.post(
                "/chat",
                headers=committed_chat_setup["owner_headers"],
                json=_chat_post_body(committed_chat_setup, content="first in flight"),
            )
        )
        await asyncio.wait_for(in_flight.wait(), timeout=15.0)

        second = await client.post(
            "/chat",
            headers=committed_chat_setup["owner_headers"],
            json=_chat_post_body(committed_chat_setup, content="must be rejected"),
        )
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "THREAD_BUSY"

        release.set()
        first = await asyncio.wait_for(first_task, timeout=15.0)
        assert first.status_code == 200, first.text

    async with committed_chat_setup["session_local"]() as db:
        human_count = await db.scalar(
            select(func.count())
            .select_from(ThreadMainMessage)
            .where(
                ThreadMainMessage.thread_id == committed_chat_setup["thread_id"],
                ThreadMainMessage.type == "human",
            )
        )
    assert human_count == 1


@pytest.mark.asyncio
async def test_racing_post_chat_admits_only_one_turn(committed_chat_setup: dict, monkeypatch):
    import httpx

    from apps.tenant_app_service.server import app

    patch_fast_agent_graph(monkeypatch)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first, second = await asyncio.gather(
            client.post(
                "/chat",
                headers=committed_chat_setup["owner_headers"],
                json=_chat_post_body(committed_chat_setup, content="race-a"),
            ),
            client.post(
                "/chat",
                headers=committed_chat_setup["owner_headers"],
                json=_chat_post_body(committed_chat_setup, content="race-b"),
            ),
        )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409], (first.text, second.text)
    for response in (first, second):
        if response.status_code == 409:
            assert response.json()["code"] == "THREAD_BUSY"

    async with committed_chat_setup["session_local"]() as db:
        human_count = await db.scalar(
            select(func.count())
            .select_from(ThreadMainMessage)
            .where(
                ThreadMainMessage.thread_id == committed_chat_setup["thread_id"],
                ThreadMainMessage.type == "human",
            )
        )
    assert human_count == 1


# Slack overlap while a turn is in-flight is covered indirectly: admission logic is shared
# with HTTP (see overlapping/racing POST /chat tests). Slack integration tests use a
# savepoint-bound DB connection that cannot safely run parallel background ingress tasks.


@pytest.mark.asyncio
async def test_different_threads_same_tenant_both_acquire_turn_lock(committed_chat_setup: dict):
    tenant_id = committed_chat_setup["tenant_id"]
    thread_a = committed_chat_setup["thread_id"]
    thread_b = f"thread-other-{uuid4().hex[:8]}"
    pg_url = committed_chat_setup["pg_url"]

    async with committed_chat_setup["session_local"]() as db:
        db.add(
            ChatThread(
                id=thread_b,
                tenant_id=tenant_id,
                user_id=committed_chat_setup["owner_id"],
                agent_id=-1,
                title="second thread",
                message_count=0,
            )
        )
        await db.commit()

    engine = create_async_engine(pg_url, future=True, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await try_acquire_thread_turn_xact_lock(session, tenant_id=tenant_id, thread_id=thread_a)
                await try_acquire_thread_turn_xact_lock(session, tenant_id=tenant_id, thread_id=thread_b)
    finally:
        await engine.dispose()
