"""Tests for durable chat thread persistence."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.core.exceptions import ValidationError
from apps.shared.schemas.user import UserDTO
from uuid import uuid4

from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain, AgentRunStatus
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.chat.turn_service import ChatTurnService
from apps.tenant_app_service.chat.application import iter_prepared_chat_stream_committed


async def _committed_stream(chat_service, chat_request, current_user, access_token=None):
    prepared = await chat_service.prepare_chat_stream(chat_request, current_user, access_token)
    async for item in iter_prepared_chat_stream_committed(
        chat_service.tenant_id,
        chat_request,
        current_user,
        prepared,
        access_token=access_token,
    ):
        yield item


def _mock_send_human_and_runs(agent_id: int = -1, thread_id: str = "thread-1"):
    run_id = str(uuid4())
    session_id = str(uuid4())
    trigger = f"human-{uuid4().hex[:8]}"
    return trigger, [
        AgentRunDomain(
            id=run_id,
            tenant_id=1,
            thread_id=thread_id,
            agent_id=agent_id,
            trigger_message_id=trigger,
            invoke_index=0,
            status=AgentRunStatus.QUEUED,
            session_id=session_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    ]

from apps.tenant_app_service.chat.streaming import (
    PreparedChatStream,
    SSE_HEARTBEAT_PAYLOAD,
    STREAM_ERROR_KIND_DOMAIN,
    STREAM_ERROR_KIND_RATE_LIMIT,
    STREAM_ERROR_KIND_TIMEOUT,
    format_user_stream_error,
    is_transient_postgres_connection_error,
    stream_error_kind,
    user_stream_error_sse_payload,
)


def _parse_sse_data_payloads(chunks: list[str]) -> list[dict]:
    payloads: list[dict] = []
    for item in chunks:
        if not item.startswith("data: "):
            continue
        payloads.append(json.loads(item.removeprefix("data: ").strip()))
    return payloads


@pytest.fixture(autouse=True)
def _noop_thread_turn_guard():
    with patch(
        "apps.tenant_app_service.chat.turn_service.guard_thread_turn_start",
        AsyncMock(),
    ):
        yield


@pytest.fixture
def chat_service():
    db = MagicMock()
    with patch(
        "apps.tenant_app_service.chat.turn_service.ThreadService.get_thread",
        AsyncMock(return_value=SimpleNamespace(agent_id=-1)),
    ):
        service = ChatTurnService(tenant_id=1, db=db)
        service._resolve_agent_id = AsyncMock(return_value=-1)
        yield service


@pytest.fixture
def thread_service(chat_service):
    return ThreadService(tenant_id=1, db=chat_service.db)


@pytest.fixture
def current_user():
    return UserDTO(
        id=10,
        username="tester",
        role="user",
        tenant_id=1,
        tenant_name="Test Tenant",
    )


@pytest.fixture
def chat_request():
    return ChatRequest(
        tenant_id=1,
        agent_id=-1,
        message=SimpleMessage(role="human", content="Hello"),
        thread_id="1_10_-1_abc",
    )


def test_build_initial_agent_messages_excludes_human_for_normal_send(chat_service, chat_request):
    lc_messages = [
        SystemMessage(content="context"),
        HumanMessage(id="human-1", content="Hello"),
    ]

    initial = chat_service._build_initial_agent_messages(lc_messages, chat_request)

    assert len(initial) == 1
    assert isinstance(initial[0], SystemMessage)


@pytest.mark.asyncio
async def test_cancel_superseded_hitl_on_normal_send(chat_service, chat_request):
    with patch("apps.tenant_app_service.hitl.service.HitlApprovalService") as svc_cls:
        svc_cls.return_value.cancel_superseded_pending_for_thread = AsyncMock(return_value=1)
        await chat_service._cancel_superseded_hitl_if_needed(chat_request)
        svc_cls.return_value.cancel_superseded_pending_for_thread.assert_awaited_once_with(chat_request.thread_id)


@pytest.mark.asyncio
async def test_chat_stream_persists_before_session_started(chat_service, chat_request, current_user):
    call_order: list[str] = []
    background_started = asyncio.Event()

    async def track_send(**kwargs):
        call_order.append("send_human")
        return _mock_send_human_and_runs(agent_id=chat_request.agent_id, thread_id=chat_request.thread_id)

    async def fake_run_agent_and_emit(**kwargs):
        call_order.append("background")
        background_started.set()
        await kwargs["event_queue"].put('data: {"type":"done","session_id":"x"}\n\n')
        await kwargs["event_queue"].put(None)

    with (
        patch.object(chat_service, "_get_system_agent_graph", AsyncMock(return_value=MagicMock(get_name=lambda: "A"))),
        patch.object(
            chat_service,
            "_inject_message_attachments",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_cancel_superseded_hitl_if_needed", AsyncMock()),
        patch.object(chat_service, "_reconcile_active_runs_before_new_turn", AsyncMock()),
        patch(
            "apps.tenant_app_service.chat.turn_service.ThreadRunService.send_human_and_create_runs",
            side_effect=track_send,
        ),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(ChatTurnService, "run_agent_and_emit_prepared", side_effect=fake_run_agent_and_emit),
        patch("apps.tenant_app_service.chat.turn_service.AgentRunRepository.set_status", AsyncMock()),
    ):
        events = []
        async for item in _committed_stream(chat_service, chat_request, current_user):
            events.append(json.loads(item.removeprefix("data: ").strip()))
        await asyncio.wait_for(background_started.wait(), timeout=1)

    assert call_order[:2] == ["send_human", "background"]
    assert events[0]["type"] == "session_started"


@pytest.mark.asyncio
async def test_chat_stream_sse_disconnect_leaves_background_running(chat_service, chat_request, current_user):
    background_started = asyncio.Event()

    async def fake_run_agent_and_emit(**kwargs):
        background_started.set()
        await asyncio.Event().wait()

    with (
        patch.object(chat_service, "_get_system_agent_graph", AsyncMock(return_value=MagicMock(get_name=lambda: "A"))),
        patch.object(
            chat_service,
            "_inject_message_attachments",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_cancel_superseded_hitl_if_needed", AsyncMock()),
        patch.object(chat_service, "_reconcile_active_runs_before_new_turn", AsyncMock()),
        patch(
            "apps.tenant_app_service.chat.turn_service.ThreadRunService.send_human_and_create_runs",
            AsyncMock(return_value=_mock_send_human_and_runs()),
        ),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(ChatTurnService, "run_agent_and_emit_prepared", side_effect=fake_run_agent_and_emit),
        patch("apps.tenant_app_service.chat.turn_service.AgentRunRepository.set_status", AsyncMock()),
    ):

        async def consume_stream():
            async for _ in _committed_stream(chat_service, chat_request, current_user):
                pass

        consumer = asyncio.create_task(consume_stream())
        await asyncio.wait_for(background_started.wait(), timeout=1)
        consumer.cancel()
        await consumer

    assert background_started.is_set()


@pytest.mark.asyncio
async def test_chat_stream_delivers_background_events(chat_service, chat_request, current_user):
    agent_graph = MagicMock()
    agent_graph.get_name.return_value = "AgentOne"

    background_started = asyncio.Event()

    async def fake_run_agent_and_emit(**kwargs):
        background_started.set()
        await kwargs["event_queue"].put('data: {"type":"done","session_id":"x"}\n\n')
        await kwargs["event_queue"].put(None)

    with (
        patch.object(chat_service, "_get_system_agent_graph", AsyncMock(return_value=agent_graph)),
        patch.object(
            chat_service,
            "_inject_message_attachments",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_cancel_superseded_hitl_if_needed", AsyncMock()),
        patch.object(chat_service, "_reconcile_active_runs_before_new_turn", AsyncMock()),
        patch(
            "apps.tenant_app_service.chat.turn_service.ThreadRunService.send_human_and_create_runs",
            AsyncMock(return_value=_mock_send_human_and_runs()),
        ),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(ChatTurnService, "run_agent_and_emit_prepared", side_effect=fake_run_agent_and_emit),
        patch("apps.tenant_app_service.chat.turn_service.AgentRunRepository.set_status", AsyncMock()),
    ):
        chunks = []
        async for item in _committed_stream(chat_service, chat_request, current_user):
            chunks.append(item)

        await asyncio.wait_for(background_started.wait(), timeout=1)

    events = _parse_sse_data_payloads(chunks)
    assert events[0]["type"] == "session_started"
    assert any(event["type"] == "done" for event in events)


@pytest.mark.asyncio
async def test_chat_stream_emits_heartbeat_while_agent_is_idle(chat_service, chat_request, current_user):
    prepared = PreparedChatStream(
        session_id="session-heartbeat",
        agent_id=-1,
        agent_name="AgentOne",
        initial_messages=[],
        thread_title=None,
    )

    async def fake_run_agent_and_emit(**kwargs):
        await asyncio.Event().wait()

    chunks: list[str] = []

    async def collect_stream():
        async for item in iter_prepared_chat_stream_committed(
            chat_service.tenant_id,
            chat_request,
            current_user,
            prepared,
        ):
            chunks.append(item)

    async def _with_same_service(_tenant_id, operation):
        return await operation(chat_service)

    with (
        patch(
            "apps.tenant_app_service.chat.application.turn_flow.with_chat_service",
            side_effect=_with_same_service,
        ),
        patch.object(ChatTurnService, "run_agent_and_emit_prepared", side_effect=fake_run_agent_and_emit),
        patch(
            "apps.tenant_app_service.chat.streaming.SSE_HEARTBEAT_INTERVAL_SECONDS",
            0.05,
        ),
    ):
        consumer = asyncio.create_task(collect_stream())
        await asyncio.sleep(0.12)
        consumer.cancel()
        await consumer

    assert SSE_HEARTBEAT_PAYLOAD in chunks


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (ValidationError("Thread is locked"), "Thread is locked"),
        (RuntimeError("429 rate limit exceeded for model"), "Rate limit exceeded. Please try again in a moment."),
        (RuntimeError("Connection timeout while calling provider"), "Request timed out. Please try again."),
        (RuntimeError(""), "Something went wrong while processing your request. Please try again."),
    ],
)
def test_format_user_stream_error_maps_known_failures(error, expected_message):
    assert format_user_stream_error(error) == expected_message


def test_is_transient_postgres_connection_error_admin_shutdown():
    class _PgOpError(Exception):
        __module__ = "psycopg.errors"

    err = _PgOpError("terminating connection due to administrator command")
    assert is_transient_postgres_connection_error(err)
    assert "Database connection lost" in format_user_stream_error(err)


@pytest.mark.parametrize(
    ("error", "expected_kind"),
    [
        (ValidationError("nope"), STREAM_ERROR_KIND_DOMAIN),
        (RuntimeError("rate limit"), STREAM_ERROR_KIND_RATE_LIMIT),
        (RuntimeError("read timeout"), STREAM_ERROR_KIND_TIMEOUT),
    ],
)
def test_stream_error_kind_is_stable_for_clients(error, expected_kind):
    assert stream_error_kind(error) == expected_kind


def test_user_stream_error_sse_payload_includes_kind_and_code():
    payload = user_stream_error_sse_payload(ValidationError("Bad input"))

    assert payload["type"] == "error"
    assert payload["message"] == "Bad input"
    assert payload["error_code"] == "ValidationError"
    assert payload["error_kind"] == STREAM_ERROR_KIND_DOMAIN


def test_stream_event_to_sse_token():
    chunk = SimpleNamespace(content="hello")
    event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}, "tags": []}
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    sse = ChatTurnService._stream_event_to_sse(event)
    assert sse is not None
    payload = json.loads(sse.removeprefix("data: ").strip())
    assert payload["type"] == "token"
    assert payload["content"] == "hello"
