"""Tests for message feedback repository upsert behavior."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.message_feedback.repository import MessageFeedbackRepository


@pytest.mark.asyncio
async def test_upsert_updates_existing_row():
    db = AsyncMock()
    repo = MessageFeedbackRepository(db)
    existing = MagicMock()
    existing.rating = "positive"
    repo.get_by_user_and_message = AsyncMock(return_value=existing)

    now = datetime.now(UTC)
    domain = await repo.upsert(
        tenant_id=1,
        thread_id="thread_a",
        session_id="session_a",
        message_id="msg_a",
        agent_id=3,
        user_id=10,
        rating="negative",
        comment="wrong answer",
        source="portal",
        external_ref=None,
        now=now,
    )

    assert domain.rating == "negative"
    assert existing.comment == "wrong answer"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_inserts_new_row_when_missing():
    db = AsyncMock()
    repo = MessageFeedbackRepository(db)
    repo.get_by_user_and_message = AsyncMock(return_value=None)

    now = datetime.now(UTC)
    await repo.upsert(
        tenant_id=1,
        thread_id="thread_a",
        session_id="session_a",
        message_id="msg_b",
        agent_id=3,
        user_id=10,
        rating="positive",
        comment=None,
        source="slack",
        external_ref={"channel_id": "C1", "message_ts": "1.23"},
        now=now,
    )

    db.add.assert_called_once()
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_aggregate_stats_returns_totals():
    db = AsyncMock()
    overall = MagicMock()
    overall.one.return_value = (4, 2)
    by_agent = MagicMock()
    by_agent.all.return_value = [(3, 3, 1)]

    db.execute = AsyncMock(side_effect=[overall, by_agent])
    repo = MessageFeedbackRepository(db)

    pos, neg, by_agent_rows = await repo.aggregate_stats(tenant_id=1, agent_id=3)

    assert pos == 4
    assert neg == 2
    assert by_agent_rows == [(3, 3, 1)]
    assert db.execute.await_count == 2
