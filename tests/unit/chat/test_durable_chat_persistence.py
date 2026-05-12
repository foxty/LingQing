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

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.service import ChatService
from apps.tenant_app_service.chat.session_status import resolve_session_status


@pytest.fixture
def chat_service():
    service = ChatService(tenant_id=1, db=MagicMock())
    service.get_thread = AsyncMock(return_value=SimpleNamespace(agent_id=-1))
    return service


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
        svc_cls.return_value.cancel_superseded_pending_for_thread.assert_awaited_once_with(
            chat_request.thread_id
        )


@pytest.mark.asyncio
async def test_cancel_superseded_hitl_skipped_for_continuation(chat_service, chat_request):
    chat_request.hitl_proposal_id = "hitl_abc"
    chat_request.hitl_action = "approved"
    with patch("apps.tenant_app_service.hitl.service.HitlApprovalService") as svc_cls:
        await chat_service._cancel_superseded_hitl_if_needed(chat_request)
        svc_cls.assert_not_called()


def test_build_initial_agent_messages_includes_human_for_hitl_continuation(chat_service, chat_request):
    chat_request.hitl_proposal_id = "hitl_abc"
    chat_request.hitl_action = "approved"
    lc_messages = [
        SystemMessage(content="context"),
        HumanMessage(id="human-1", content="continue hitl workflow"),
    ]

    initial = chat_service._build_initial_agent_messages(lc_messages, chat_request)

    assert len(initial) == 2


@pytest.mark.asyncio
async def test_persist_incoming_human_message_calls_manager(chat_service):
    human = HumanMessage(id="human-1", content="Hello")
    config = {
        "configurable": {
            "runtime": {
                "session_id": "session-1",
                "agent_id": -1,
                "thread_id": "thread-1",
                "user": {"id": 1, "username": "u", "role": "user", "tenant_id": 1, "tenant_name": "t"},
                "tenant": {"tenant_id": 1, "tenant_name": "t", "config": {}},
                "agent_name": "agent",
            }
        }
    }

    mock_manager = MagicMock()
    mock_manager.add_messages = AsyncMock()
    runtime = MagicMock(session_id="session-1", agent_id=-1)

    with (
        patch(
            "apps.tenant_app_service.chat.streaming.extract_runtime_context",
            return_value=runtime,
        ),
        patch(
            "apps.tenant_app_service.agents.memory.conversation_memory_manager.ConversationMemoryManager",
            return_value=mock_manager,
        ),
    ):
        await chat_service._persist_incoming_human_message(
            lc_messages=[human],
            config=config,
            thread_id="thread-1",
        )

    mock_manager.add_messages.assert_awaited_once_with([human], config, deduplicate=True)


@pytest.mark.asyncio
async def test_get_session_status_returns_awaiting_hitl(chat_service):
    pending = SimpleNamespace(
        proposal_id="hitl_1",
        tool_name="bash",
        session_id="session-hitl",
    )

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=pending)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)
        chat_service.message_repo.has_ai_message_for_session = AsyncMock(return_value=True)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "awaiting_hitl"
    assert status.pending_hitl is not None
    assert status.pending_hitl.proposal_id == "hitl_1"


@pytest.mark.asyncio
async def test_get_session_status_returns_running_when_human_without_ai(chat_service):
    latest_human = SimpleNamespace(
        session_id="session-running",
        created_at=datetime.now(UTC),
    )

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)

        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=latest_human)
        chat_service.message_repo.has_ai_message_for_session = AsyncMock(return_value=False)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "running"
    assert status.session_id == "session-running"
    assert status.has_ai_response is False


@pytest.mark.asyncio
async def test_get_session_status_completed_when_orphaned_run_is_stale(chat_service):
    latest_human = SimpleNamespace(
        session_id="session-stale",
        created_at=datetime.now(UTC) - timedelta(minutes=20),
    )

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)

        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=latest_human)
        chat_service.message_repo.has_ai_message_for_session = AsyncMock(return_value=False)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "completed"
    assert status.has_ai_response is False


@pytest.mark.asyncio
async def test_get_session_status_returns_completed_when_human_has_ai(chat_service):
    latest_human = SimpleNamespace(session_id="session-done")

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)

        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=latest_human)
        chat_service.message_repo.has_ai_message_for_session = AsyncMock(return_value=True)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "completed"
    assert status.has_ai_response is True


@pytest.mark.asyncio
async def test_get_session_status_returns_hitl_approved_pending_continue(chat_service):
    approved = SimpleNamespace(
        proposal_id="hitl_approved",
        tool_name="bash",
        session_id="session-old",
        approved_at=datetime.now(UTC),
    )

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=approved)

        chat_service.message_repo.has_messages_after_timestamp = AsyncMock(return_value=False)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "hitl_approved_pending_continue"
    assert status.approved_hitl is not None
    assert status.approved_hitl.proposal_id == "hitl_approved"


@pytest.mark.asyncio
async def test_pending_hitl_takes_priority_over_running_human(chat_service):
    pending = SimpleNamespace(
        proposal_id="hitl_1",
        tool_name="bash",
        session_id="session-hitl",
    )
    latest_human = SimpleNamespace(session_id="session-running")

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=pending)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)
        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=latest_human)
        chat_service.message_repo.has_ai_message_for_session = AsyncMock(return_value=False)

        status = await resolve_session_status(
            tenant_id=1,
            db=chat_service.db,
            message_repo=chat_service.message_repo,
            thread_id="thread-1",
            agent_id=-1,
        )

    assert status.status == "awaiting_hitl"
    chat_service.message_repo.get_latest_human_message.assert_not_called()


@pytest.mark.asyncio
async def test_hitl_approved_with_followup_is_not_pending_continue(chat_service):
    approved = SimpleNamespace(
        proposal_id="hitl_approved",
        tool_name="bash",
        session_id="session-old",
        approved_at=datetime.now(UTC),
    )
    latest_human = SimpleNamespace(session_id="session-new")

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=approved)
        chat_service.message_repo.has_messages_after_timestamp = AsyncMock(return_value=True)
        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=latest_human)
        chat_service.message_repo.has_ai_message_for_session = AsyncMock(return_value=True)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "completed"


@pytest.mark.asyncio
async def test_get_session_status_completed_when_no_human(chat_service):
    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)
        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=None)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "completed"


@pytest.mark.asyncio
async def test_get_session_status_completed_when_human_has_no_session_id(chat_service):
    latest_human = SimpleNamespace(session_id=None)

    with patch("apps.tenant_app_service.chat.session_status.HitlApprovalRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_latest_pending_by_thread = AsyncMock(return_value=None)
        repo.get_latest_approved_by_thread = AsyncMock(return_value=None)
        chat_service.message_repo.get_latest_human_message = AsyncMock(return_value=latest_human)

        status = await chat_service.get_session_status(thread_id="thread-1", agent_id=-1)

    assert status.status == "completed"


@pytest.mark.asyncio
async def test_chat_stream_persists_before_session_started(chat_service, chat_request, current_user):
    call_order: list[str] = []
    background_started = asyncio.Event()

    async def track_persist(**kwargs):
        call_order.append("persist")

    async def fake_run_agent_and_emit(**kwargs):
        call_order.append("background")
        background_started.set()
        await kwargs["event_queue"].put('data: {"type":"done","session_id":"x"}\n\n')
        await kwargs["event_queue"].put(None)

    with (
        patch.object(chat_service, "_get_system_agent_graph", AsyncMock(return_value=MagicMock(get_name=lambda: "A"))),
        patch.object(
            chat_service,
            "_inject_selected_context_resources",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "_get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_cancel_superseded_hitl_if_needed", AsyncMock()),
        patch.object(chat_service, "_persist_incoming_human_message", side_effect=track_persist),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(chat_service, "_run_agent_and_emit", side_effect=fake_run_agent_and_emit),
    ):
        events = []
        async for item in chat_service.chat_stream(chat_request, current_user):
            events.append(json.loads(item.removeprefix("data: ").strip()))
        await asyncio.wait_for(background_started.wait(), timeout=1)

    assert call_order[:2] == ["persist", "background"]
    assert events[0]["type"] == "session_started"


@pytest.mark.asyncio
async def test_chat_stream_skips_persist_for_hitl_continuation(chat_service, chat_request, current_user):
    chat_request.hitl_proposal_id = "hitl_abc"
    chat_request.hitl_action = "approved"
    persist_mock = AsyncMock()

    async def fake_run_agent_and_emit(**kwargs):
        await kwargs["event_queue"].put(None)

    with (
        patch.object(chat_service, "_get_system_agent_graph", AsyncMock(return_value=MagicMock(get_name=lambda: "A"))),
        patch.object(
            chat_service,
            "_inject_selected_context_resources",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "_get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_persist_incoming_human_message", persist_mock),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(chat_service, "_run_agent_and_emit", side_effect=fake_run_agent_and_emit),
    ):
        async for _ in chat_service.chat_stream(chat_request, current_user):
            pass

    persist_mock.assert_not_called()


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
            "_inject_selected_context_resources",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "_get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_cancel_superseded_hitl_if_needed", AsyncMock()),
        patch.object(chat_service, "_persist_incoming_human_message", AsyncMock()),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(chat_service, "_run_agent_and_emit", side_effect=fake_run_agent_and_emit),
    ):

        async def consume_stream():
            async for _ in chat_service.chat_stream(chat_request, current_user):
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
            "_inject_selected_context_resources",
            AsyncMock(side_effect=lambda msgs, *a, **k: msgs),
        ),
        patch.object(
            chat_service,
            "_get_tenant_domain",
            AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=lambda: {}))),
        ),
        patch.object(
            chat_service,
            "_build_runtime_config",
            return_value={"configurable": {"thread_id": chat_request.thread_id}},
        ),
        patch.object(chat_service, "_cancel_superseded_hitl_if_needed", AsyncMock()),
        patch.object(chat_service, "_persist_incoming_human_message", AsyncMock()),
        patch.object(chat_service, "create_thread_title_if_1st_message", AsyncMock(return_value=None)),
        patch.object(chat_service, "_run_agent_and_emit", side_effect=fake_run_agent_and_emit),
    ):
        events = []
        async for item in chat_service.chat_stream(chat_request, current_user):
            events.append(json.loads(item.removeprefix("data: ").strip()))

        await asyncio.wait_for(background_started.wait(), timeout=1)

    assert events[0]["type"] == "session_started"
    assert any(event["type"] == "done" for event in events)


def test_stream_event_to_sse_token():
    chunk = SimpleNamespace(content="hello")
    event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}, "tags": []}
    sse = ChatService._stream_event_to_sse(event)
    assert sse is not None
    payload = json.loads(sse.removeprefix("data: ").strip())
    assert payload["type"] == "token"
    assert payload["content"] == "hello"
