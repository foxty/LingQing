"""Chat router releases the app DB session before long agent/SSE waits."""

from types import SimpleNamespace

import pytest
from fastapi.responses import StreamingResponse

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse, Message, SimpleMessage
from apps.tenant_app_service.chat.streaming import PreparedChatStream
from apps.tenant_app_service.routers import chat as chat_router


def _user() -> UserDTO:
    return UserDTO(id=7, username="tester", role="admin", tenant_id=1, tenant_name="test_tenant")


def _request() -> ChatRequest:
    return ChatRequest(
        tenant_id=1,
        agent_id=-1,
        message=SimpleMessage(role="human", content="Hello"),
        thread_id="thread-1",
    )


class _TrackingSession:
    def __init__(self, events: list[str]):
        self._events = events

    async def __aenter__(self):
        self._events.append("session_enter")
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        self._events.append("session_exit")
        return False


@pytest.mark.asyncio
async def test_chat_uses_short_session_around_invoke(monkeypatch):
    events: list[str] = []

    async def _validate(thread_id, current_user, db):
        events.append("validate")

    class _Service:
        def __init__(self, tenant_id, db):
            _ = tenant_id, db

        async def chat(self, request, current_user, access_token=None):
            events.append("invoke")
            return ChatResponse(
                response=Message(role="ai", content="ok", agent_id=-1, thread_id="thread-1"),
                agent_id=-1,
                tenant_id=1,
            )

    monkeypatch.setattr(chat_router, "app_db_session", lambda: _TrackingSession(events))
    monkeypatch.setattr(chat_router, "_validate_and_get_thread", _validate)
    monkeypatch.setattr(chat_router, "ChatService", _Service)

    result = await chat_router.chat(
        request=_request(),
        current_user=_user(),
        credentials=SimpleNamespace(credentials="token"),
    )

    assert result.response.content == "ok"
    assert events == ["session_enter", "validate", "invoke", "session_exit"]


@pytest.mark.asyncio
async def test_chat_stream_releases_session_before_sse_iter(monkeypatch):
    events: list[str] = []
    prepared = PreparedChatStream(
        session_id="session-1",
        agent_id=-1,
        agent_name="Agent",
        initial_messages=[],
        thread_title=None,
    )

    async def _validate(thread_id, current_user, db):
        events.append("validate")

    class _Service:
        def __init__(self, tenant_id, db):
            _ = tenant_id, db

        async def prepare_chat_stream(self, request, current_user, access_token=None):
            events.append("prepare")
            return prepared

        async def iter_prepared_chat_stream(self, request, current_user, prepared_stream, access_token=None):
            events.append("iter")
            yield 'data: {"type":"done","session_id":"session-1"}\n\n'

    monkeypatch.setattr(chat_router, "app_db_session", lambda: _TrackingSession(events))
    monkeypatch.setattr(chat_router, "_validate_and_get_thread", _validate)
    monkeypatch.setattr(chat_router, "ChatService", _Service)

    response = await chat_router.chat_stream(
        request=_request(),
        current_user=_user(),
        credentials=SimpleNamespace(credentials="token"),
    )

    assert isinstance(response, StreamingResponse)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert events == ["session_enter", "validate", "prepare", "session_exit", "iter"]
    assert any("session-1" in chunk for chunk in chunks)
