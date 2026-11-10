"""Tests for message feedback service."""

import csv
import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.tenant_app_service.message_feedback.domain import FEEDBACK_COMMENT_MAX_LENGTH
from apps.tenant_app_service.message_feedback.domain import (
    FEEDBACK_RATING_POSITIVE,
    FEEDBACK_SOURCE_PORTAL,
)
from apps.tenant_app_service.message_feedback import service as feedback_service_module
from apps.tenant_app_service.message_feedback.service import MessageFeedbackService, iter_feedback_export_csv

_THREAD_GET = "apps.tenant_app_service.message_feedback.service.ThreadService.get_thread"


@pytest.mark.asyncio
async def test_upsert_feedback_rejects_comment_over_max_length():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        get_thread.return_value = MagicMock(user_id=10)
        service = MessageFeedbackService(tenant_id=1, db=db)
        service.repository = MagicMock()
        ai_message = MagicMock()
        ai_message.thread_id = "thread_a"
        service.repository.get_ai_message = AsyncMock(return_value=ai_message)

        with pytest.raises(ValidationError):
            await service.upsert_feedback(
                thread_id="thread_a",
                message_id="msg_a",
                user_id=10,
                rating=FEEDBACK_RATING_POSITIVE,
                comment="x" * (FEEDBACK_COMMENT_MAX_LENGTH + 1),
            )


@pytest.mark.asyncio
async def test_upsert_feedback_validates_rating_before_thread_lookup():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        service = MessageFeedbackService(tenant_id=1, db=db)
        with pytest.raises(ValidationError):
            await service.upsert_feedback(
                thread_id="thread_a",
                message_id="msg_a",
                user_id=10,
                rating="invalid",  # type: ignore[arg-type]
            )
        get_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_feedback_requires_ai_message_in_thread():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        get_thread.return_value = MagicMock(user_id=10)
        service = MessageFeedbackService(tenant_id=1, db=db)
        service.repository = MagicMock()
        service.repository.get_ai_message = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundError):
            await service.upsert_feedback(
                thread_id="thread_a",
                message_id="msg_a",
                user_id=10,
                rating=FEEDBACK_RATING_POSITIVE,
            )


@pytest.mark.asyncio
async def test_upsert_feedback_enforces_thread_owner_via_thread_service():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        get_thread.return_value = MagicMock(user_id=99)
        service = MessageFeedbackService(tenant_id=1, db=db)
        service.repository = MagicMock()
        ai_message = MagicMock()
        ai_message.thread_id = "thread_a"
        service.repository.get_ai_message = AsyncMock(return_value=ai_message)

        with pytest.raises(AuthorizationError):
            await service.upsert_feedback(
                thread_id="thread_a",
                message_id="msg_a",
                user_id=10,
                rating=FEEDBACK_RATING_POSITIVE,
            )
        get_thread.assert_awaited_once_with("thread_a")


@pytest.mark.asyncio
async def test_upsert_feedback_persists_rating():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        get_thread.return_value = MagicMock(user_id=10)
        service = MessageFeedbackService(tenant_id=1, db=db)

        ai_message = MagicMock()
        ai_message.thread_id = "thread_a"
        ai_message.session_id = "session_a"
        ai_message.agent_id = 5

        now = datetime.now(UTC)
        service.repository = MagicMock()
        service.repository.get_ai_message = AsyncMock(return_value=ai_message)
        service.repository.upsert = AsyncMock(
            return_value=MagicMock(
                id=1,
                tenant_id=1,
                thread_id="thread_a",
                session_id="session_a",
                message_id="msg_a",
                agent_id=5,
                user_id=10,
                rating=FEEDBACK_RATING_POSITIVE,
                comment=None,
                source=FEEDBACK_SOURCE_PORTAL,
                external_ref=None,
                created_at=now,
                updated_at=now,
            )
        )

        result = await service.upsert_feedback(
            thread_id="thread_a",
            message_id="msg_a",
            user_id=10,
            rating=FEEDBACK_RATING_POSITIVE,
        )

        assert result.rating == FEEDBACK_RATING_POSITIVE
        get_thread.assert_awaited_once_with("thread_a")
        service.repository.upsert.assert_awaited_once()
        db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_comment_requires_thread_access():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        get_thread.return_value = MagicMock(user_id=99)
        service = MessageFeedbackService(tenant_id=1, db=db)
        service.repository = MagicMock()
        existing_row = MagicMock()
        existing_row.thread_id = "thread_a"
        service.repository.get_by_user_and_message = AsyncMock(return_value=existing_row)

        with pytest.raises(AuthorizationError):
            await service.update_comment(message_id="msg_a", user_id=10, comment="note")
        get_thread.assert_awaited_once_with("thread_a")


@pytest.mark.asyncio
async def test_resolve_message_context_uses_thread_agent_when_message_has_none():
    db = AsyncMock()
    with patch(_THREAD_GET, new_callable=AsyncMock) as get_thread:
        get_thread.return_value = MagicMock(agent_id=5)
        service = MessageFeedbackService(tenant_id=1, db=db)
        service.repository = MagicMock()
        ai_message = MagicMock()
        ai_message.thread_id = "thread_a"
        ai_message.agent_id = None
        ai_message.session_id = "session_a"
        ai_message.id = 77
        service.repository.get_ai_message = AsyncMock(return_value=ai_message)

        thread_id, agent_id, session_id, db_id = await service.resolve_message_context("msg_a")

        assert thread_id == "thread_a"
        assert agent_id == 5
        assert session_id == "session_a"
        assert db_id == 77
        get_thread.assert_awaited_once_with("thread_a")


@pytest.mark.asyncio
async def test_list_feedback_batches_message_lookups():
    db = AsyncMock()
    service = MessageFeedbackService(tenant_id=1, db=db)
    service.repository = MagicMock()

    row = MagicMock()
    row.id = 10
    row.thread_id = "thread_a"
    row.session_id = "session_a"
    row.message_id = "msg_a"
    row.agent_id = 3
    row.user_id = 7
    row.rating = "positive"
    row.comment = None
    row.source = "portal"
    row.created_at = datetime.now(UTC)

    service.repository.list_paginated = AsyncMock(return_value=([ (row, "alice") ], False))
    from apps.tenant_app_service.message_feedback.domain import FeedbackTargetMessage

    ai_message = FeedbackTargetMessage(
        id=1,
        message_id="msg_a",
        thread_id="thread_a",
        session_id="session_a",
        agent_id=3,
        content="AI reply",
        trigger_message_id="human_msg_a",
    )
    service.repository.get_ai_messages_by_ids = AsyncMock(return_value={"msg_a": ai_message})
    service.repository.get_human_contents_by_triggers = AsyncMock(
        return_value={("thread_a", "human_msg_a"): "Human question"}
    )
    service.repository.get_human_previews_for_sessions = AsyncMock(return_value={})

    result = await service.list_feedback()

    assert len(result.items) == 1
    assert result.items[0].ai_message_preview == "AI reply"
    assert result.items[0].human_message_preview == "Human question"
    service.repository.get_ai_messages_by_ids.assert_awaited_once_with(1, ["msg_a"])
    service.repository.get_human_contents_by_triggers.assert_awaited_once()


@pytest.mark.asyncio
async def test_export_feedback_csv_includes_full_message_text(monkeypatch):
    mock_repo = MagicMock()
    long_ai = "x" * 250
    long_human = "h" * 250
    row = MagicMock()
    row.id = 10
    row.thread_id = "thread_a"
    row.session_id = "session_a"
    row.message_id = "msg_a"
    row.agent_id = 3
    row.user_id = 7
    row.rating = "positive"
    row.comment = None
    row.source = "portal"
    row.created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    mock_repo.list_paginated = AsyncMock(return_value=([(row, "alice")], False))
    from apps.tenant_app_service.message_feedback.domain import FeedbackTargetMessage

    ai_target = FeedbackTargetMessage(
        id=1,
        message_id="msg_a",
        thread_id="thread_a",
        session_id="session_a",
        agent_id=3,
        content=long_ai,
        trigger_message_id="human_msg_a",
    )
    mock_repo.get_ai_messages_by_ids = AsyncMock(return_value={"msg_a": ai_target})
    mock_repo.get_human_contents_by_triggers = AsyncMock(
        return_value={("thread_a", "human_msg_a"): long_human}
    )
    mock_repo.get_human_previews_for_sessions = AsyncMock(return_value={})

    class _StubFeedbackService(MessageFeedbackService):
        def __init__(self, tenant_id: int, db: object) -> None:
            self.tenant_id = tenant_id
            self.repository = mock_repo

    @asynccontextmanager
    async def _fake_db_session():
        yield AsyncMock()

    monkeypatch.setattr(feedback_service_module, "MessageFeedbackService", _StubFeedbackService)
    monkeypatch.setattr(feedback_service_module, "app_db_session", _fake_db_session)

    chunks = [chunk async for chunk in iter_feedback_export_csv(1)]
    csv_text = b"".join(chunks).decode()

    parsed = list(csv.reader(io.StringIO(csv_text)))
    assert parsed[0][-3:-1] == ["human_message", "ai_message"]
    assert parsed[1][-3] == long_human
    assert parsed[1][-2] == long_ai
    assert "..." not in parsed[1][-2]
    mock_repo.get_human_contents_by_triggers.assert_awaited_once()
    _, kwargs = mock_repo.get_human_contents_by_triggers.await_args
    assert kwargs.get("truncate") is False


@pytest.mark.asyncio
async def test_export_feedback_opens_db_session_per_page(monkeypatch):
    session_opens = 0
    row_a = MagicMock(id=2)
    row_b = MagicMock(id=1)
    for row in (row_a, row_b):
        row.thread_id = "thread_a"
        row.session_id = "session_a"
        row.message_id = "msg"
        row.agent_id = 1
        row.user_id = 1
        row.rating = "positive"
        row.comment = None
        row.source = "portal"
        row.created_at = datetime(2026, 1, 2, tzinfo=UTC)

    mock_repo = MagicMock()
    mock_repo.list_paginated = AsyncMock(
        side_effect=[
            ([(row_a, "alice")], True),
            ([(row_b, "bob")], False),
        ]
    )
    mock_repo.get_ai_messages_by_ids = AsyncMock(return_value={})
    mock_repo.get_human_contents_by_triggers = AsyncMock(return_value={})
    mock_repo.get_human_previews_for_sessions = AsyncMock(return_value={})

    class _StubFeedbackService(MessageFeedbackService):
        def __init__(self, tenant_id: int, db: object) -> None:
            self.tenant_id = tenant_id
            self.repository = mock_repo

    @asynccontextmanager
    async def _fake_db_session():
        nonlocal session_opens
        session_opens += 1
        yield AsyncMock()

    monkeypatch.setattr(feedback_service_module, "MessageFeedbackService", _StubFeedbackService)
    monkeypatch.setattr(feedback_service_module, "app_db_session", _fake_db_session)

    chunks = [chunk async for chunk in iter_feedback_export_csv(1)]
    assert len(chunks) >= 2
    assert session_opens == 2
