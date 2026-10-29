"""Tests for message feedback repository AI message resolution."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.message_feedback.repository import MessageFeedbackRepository


@pytest.mark.asyncio
async def test_get_ai_message_prefers_thread_main_messages():
    db = AsyncMock()
    main_row = MagicMock()
    main_row.id = 10
    main_row.message_id = "lc_run--abc-0"
    main_row.thread_id = "1_3_1_uuid"
    main_row.session_id = "sess_1"
    main_row.agent_id = 1

    main_result = MagicMock()
    main_result.scalars.return_value = iter([main_row])

    db.execute = AsyncMock(return_value=main_result)

    repo = MessageFeedbackRepository(db)
    found = await repo.get_ai_message(1, "lc_run--abc-0")

    assert found is not None
    assert found.message_id == "lc_run--abc-0"
    assert found.thread_id == "1_3_1_uuid"
    assert db.execute.await_count == 1
