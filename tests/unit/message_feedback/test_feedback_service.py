"""Tests for message feedback service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.tenant_app_service.message_feedback.domain import (
    FEEDBACK_RATING_POSITIVE,
    FEEDBACK_SOURCE_PORTAL,
)
from apps.tenant_app_service.message_feedback.service import MessageFeedbackService

_THREAD_GET = "apps.tenant_app_service.message_feedback.service.ThreadService.get_thread"
_ENSURE_ACCESS = (
    "apps.tenant_app_service.message_feedback.service.MessageFeedbackService._ensure_thread_access"
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
async def test_upsert_feedback_enforces_thread_access():
    db = AsyncMock()
    with patch(_ENSURE_ACCESS, new_callable=AsyncMock) as ensure_access:
        ensure_access.side_effect = AuthorizationError("Access denied")
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
        ensure_access.assert_awaited_once_with("thread_a", 10)


@pytest.mark.asyncio
async def test_upsert_feedback_persists_rating():
    db = AsyncMock()
    with patch(_ENSURE_ACCESS, new_callable=AsyncMock) as ensure_access:
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
        ensure_access.assert_awaited_once_with("thread_a", 10)
        service.repository.upsert.assert_awaited_once()
        db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_comment_requires_thread_access():
    db = AsyncMock()
    with patch(_ENSURE_ACCESS, new_callable=AsyncMock) as ensure_access:
        ensure_access.side_effect = AuthorizationError("Access denied")
        service = MessageFeedbackService(tenant_id=1, db=db)
        service.repository = MagicMock()
        existing_row = MagicMock()
        existing_row.thread_id = "thread_a"
        service.repository.get_by_user_and_message = AsyncMock(return_value=existing_row)

        with pytest.raises(AuthorizationError):
            await service.update_comment(message_id="msg_a", user_id=10, comment="note")
        ensure_access.assert_awaited_once_with("thread_a", 10)


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
    ai_message = MagicMock()
    ai_message.content = "AI reply"
    service.repository.get_ai_messages_by_ids = AsyncMock(return_value={"msg_a": ai_message})
    service.repository.get_human_previews_for_sessions = AsyncMock(
        return_value={("thread_a", "session_a"): "Human question"}
    )

    result = await service.list_feedback()

    assert len(result.items) == 1
    assert result.items[0].ai_message_preview == "AI reply"
    assert result.items[0].human_message_preview == "Human question"
    service.repository.get_ai_messages_by_ids.assert_awaited_once_with(1, ["msg_a"])
    service.repository.get_human_previews_for_sessions.assert_awaited_once()
