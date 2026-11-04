"""Unit tests for cumulative thread-summary watermark rules."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.agents.memory.memory_budget import THREAD_SUMMARY_MIN_AGED_PAIRS
from apps.tenant_app_service.chat.domain import (
    ThreadMainMessageDomain,
    aged_out_uncovered_turns,
    context_pair_turns,
    sort_timeline_trigger_anchored,
)
from apps.tenant_app_service.chat.thread_summary_manager import (
    ThreadSummaryManager,
    should_write_thread_summary_delta,
)


def _human(message_id: str, row_id: int) -> ThreadMainMessageDomain:
    stamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return ThreadMainMessageDomain(
        id=row_id,
        message_id=message_id,
        thread_id="thread-1",
        type="human",
        content=f"ask {message_id}",
        timestamp=stamp,
        created_at=stamp,
    )


def _ai(message_id: str, trigger: str, row_id: int) -> ThreadMainMessageDomain:
    stamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return ThreadMainMessageDomain(
        id=row_id,
        message_id=message_id,
        thread_id="thread-1",
        type="ai",
        content=f"answer {message_id}",
        timestamp=stamp,
        agent_id=1,
        trigger_message_id=trigger,
        agent_run_id=f"run-{trigger}",
        created_at=stamp,
    )


def _pairs(count: int) -> list[ThreadMainMessageDomain]:
    rows: list[ThreadMainMessageDomain] = []
    for index in range(count):
        human_id = f"h{index}"
        rows.append(_human(human_id, index * 2 + 1))
        rows.append(_ai(f"a{index}", human_id, index * 2 + 2))
    return sort_timeline_trigger_anchored(rows)


def test_aged_out_skips_reserved_tail_and_pairs_already_covered():
    rows = _pairs(6)
    delta = aged_out_uncovered_turns(
        rows,
        reserve_tail=4,
        through_trigger_message_id=None,
    )
    assert [turn[0].message_id for turn in delta] == ["h0", "h1"]

    covered = aged_out_uncovered_turns(
        rows,
        reserve_tail=4,
        through_trigger_message_id="h1",
    )
    assert covered == []


def test_just_finished_pair_stays_in_the_tail():
    rows = _pairs(5)
    delta = aged_out_uncovered_turns(
        rows,
        reserve_tail=4,
        through_trigger_message_id="h0",
    )
    assert delta == []


def test_context_keeps_tail_even_when_watermark_covers_it():
    turns = []
    rows = _pairs(6)
    current: list[ThreadMainMessageDomain] = []
    for row in rows:
        if row.type == "human" and current:
            turns.append(current)
            current = []
        current.append(row)
    turns.append(current)

    kept = context_pair_turns(
        turns,
        through_trigger_message_id="h5",
        reserve_tail=4,
    )
    assert [turn[0].message_id for turn in kept] == ["h2", "h3", "h4", "h5"]


def test_context_keeps_unsummarized_pairs_between_watermark_and_tail():
    turns = []
    rows = _pairs(6)
    current: list[ThreadMainMessageDomain] = []
    for row in rows:
        if row.type == "human" and current:
            turns.append(current)
            current = []
        current.append(row)
    turns.append(current)

    kept = context_pair_turns(
        turns,
        through_trigger_message_id="h0",
        reserve_tail=2,
    )
    assert [turn[0].message_id for turn in kept] == ["h1", "h2", "h3", "h4", "h5"]


def _manager() -> ThreadSummaryManager:
    db = AsyncMock()
    db.get.return_value = MagicMock(summary_count=0)
    manager = ThreadSummaryManager(db, tenant_id=1)
    manager.main_repo = AsyncMock()
    manager.repo = AsyncMock()
    manager.repo.get_recent_summaries.return_value = []
    manager.repo.get_latest_version.return_value = 0
    manager.run_summary_repo = AsyncMock()
    manager.run_summary_repo.get_for_run.return_value = None
    manager.run_message_repo = AsyncMock()
    manager.run_message_repo.list_for_run.return_value = []
    manager._summarize = AsyncMock(return_value="status")
    return manager


@pytest.mark.asyncio
async def test_manager_does_not_summarize_while_every_pair_is_in_the_tail():
    manager = _manager()
    manager.main_repo.list_for_thread.return_value = _pairs(4)

    created = await manager.check_and_create_if_needed("thread-1")

    assert created is None
    manager._summarize.assert_not_called()


@pytest.mark.asyncio
async def test_manager_defers_when_only_one_pair_has_aged_out():
    manager = _manager()
    manager.main_repo.list_for_thread.return_value = _pairs(5)

    created = await manager.check_and_create_if_needed("thread-1")

    assert created is None
    manager._summarize.assert_not_called()


@pytest.mark.asyncio
async def test_manager_summarizes_when_two_pairs_have_aged_out():
    manager = _manager()
    manager.main_repo.list_for_thread.return_value = _pairs(6)

    created = await manager.check_and_create_if_needed("thread-1")

    assert created is not None
    saved = manager.repo.create.await_args.args[0]
    assert saved.through_trigger_message_id == "h1"
    assert saved.summary_content == "status"
    manager.db.commit.assert_awaited()


def test_should_write_batches_at_min_aged_pairs():
    rows = _pairs(6)
    delta = aged_out_uncovered_turns(rows, reserve_tail=4, through_trigger_message_id=None)
    assert len(delta) >= THREAD_SUMMARY_MIN_AGED_PAIRS
    write, reason = should_write_thread_summary_delta(
        delta=delta,
        previous_summary=None,
        main_rows=rows,
        through_trigger_message_id=None,
    )
    assert write is True
    assert reason == "batch_threshold"


def test_should_defer_single_aged_pair_without_pressure():
    rows = _pairs(5)
    delta = aged_out_uncovered_turns(rows, reserve_tail=4, through_trigger_message_id=None)
    assert len(delta) == 1
    write, reason = should_write_thread_summary_delta(
        delta=delta,
        previous_summary="short prior status",
        main_rows=rows,
        through_trigger_message_id=None,
    )
    assert write is False
    assert reason == "defer_batch"

