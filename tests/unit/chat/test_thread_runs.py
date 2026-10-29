"""Unit tests for thread main timeline and agent run orchestration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from apps.tenant_app_service.chat.agent_run_domain import (
    AgentRunStatus,
    ThreadMainMessageDomain,
    drop_run_rows_duplicating_promoted_main,
    run_status_allows_session_summary,
    exclude_trigger_human_from_main_rows,
    filter_main_timeline_for_context_load,
    slice_main_timeline_turns,
    sort_timeline_trigger_anchored,
)
from tests.unit.chat.main_timeline_pair_assertions import assert_main_timeline_summary_pairs_consistent
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService


def _human(msg_id: str, created_at: datetime, *, row_id: int, content: str = "hi") -> ThreadMainMessageDomain:
    return ThreadMainMessageDomain(
        id=row_id,
        message_id=msg_id,
        thread_id="t1",
        type="human",
        content=content,
        timestamp=created_at,
        created_at=created_at,
    )


def _ai(
    msg_id: str,
    trigger: str,
    *,
    row_id: int,
    invoke_index: int = 0,
    created_at: datetime,
    session_id: str | None = None,
) -> ThreadMainMessageDomain:
    return ThreadMainMessageDomain(
        id=row_id,
        message_id=msg_id,
        thread_id="t1",
        type="ai",
        content="reply",
        timestamp=created_at,
        agent_id=1,
        trigger_message_id=trigger,
        invoke_index=invoke_index,
        session_id=session_id,
        agent_run_id=str(uuid4()),
        created_at=created_at,
    )


def test_sort_timeline_trigger_anchored_ab_completes_out_of_order():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 0, 3, tzinfo=UTC)

    rows = [
        _human("hA", t0, row_id=1),
        _human("hB", t1, row_id=2),
        _ai("aB", "hB", row_id=4, created_at=t3),
        _ai("aA", "hA", row_id=3, created_at=t2),
    ]
    ordered = sort_timeline_trigger_anchored(rows)
    assert [m.message_id for m in ordered] == ["hA", "aA", "hB", "aB"]


def test_sort_timeline_invoke_index_siblings():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 6, tzinfo=UTC)
    rows = [
        _human("h1", t0, row_id=1),
        _ai("a1", "h1", row_id=3, invoke_index=1, created_at=t2),
        _ai("a0", "h1", row_id=2, invoke_index=0, created_at=t1),
    ]
    ordered = sort_timeline_trigger_anchored(rows)
    assert [m.message_id for m in ordered] == ["h1", "a0", "a1"]


def _filter_and_assert_pairs(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    covered: frozenset[str],
) -> list[ThreadMainMessageDomain]:
    ordered = sort_timeline_trigger_anchored(rows)
    filtered = filter_main_timeline_for_context_load(
        ordered,
        agent_id=agent_id,
        covered_session_ids=covered,
    )
    assert_main_timeline_summary_pairs_consistent(
        ordered,
        filtered,
        agent_id=agent_id,
        covered_session_ids=covered,
    )
    return filtered


def test_filter_main_timeline_drops_covered_turn_human_and_ai():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _human("h1", t0, row_id=1),
        _ai("a1", "h1", row_id=2, created_at=t0, session_id="sess-old"),
    ]
    assert _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset({"sess-old"})) == []


def test_exclude_trigger_human_from_main_rows():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _human("h1", t0, row_id=1),
        _ai("a1", "h1", row_id=2, created_at=t0),
        _human("h2", t0, row_id=3, content="current"),
    ]
    excluded = exclude_trigger_human_from_main_rows(rows, trigger_message_id="h2")
    assert [m.message_id for m in excluded] == ["h1", "a1"]


def test_filter_main_timeline_drops_human_when_legacy_ai_missing_trigger():
    """Legacy promoted AI without trigger_message_id still pairs with preceding human."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    legacy_ai = ThreadMainMessageDomain(
        id=2,
        message_id="a1",
        thread_id="t1",
        type="ai",
        content="reply",
        timestamp=t1,
        agent_id=1,
        trigger_message_id=None,
        session_id="sess-covered",
        created_at=t1,
    )
    rows = [_human("h1", t0, row_id=1), legacy_ai]
    assert _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset({"sess-covered"})) == []


def test_filter_main_timeline_drops_all_agent_ai_siblings_when_any_invoke_covered():
    """Summarized invoke drops the whole trigger turn, not only the covered AI row."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1),
            _ai("a0", "h1", row_id=2, invoke_index=0, created_at=t1, session_id="sess-covered"),
            _ai("a1", "h1", row_id=3, invoke_index=1, created_at=t2, session_id="sess-open"),
        ]
    )
    assert _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset({"sess-covered"})) == []


def test_filter_main_timeline_omits_human_when_agent_never_replied():
    """Peer agent answered; this agent has no promoted AI — human is not LLM context."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1),
            ThreadMainMessageDomain(
                id=2,
                message_id="a-other",
                thread_id="t1",
                type="ai",
                content="reply",
                timestamp=t1,
                agent_id=99,
                trigger_message_id="h1",
                session_id="sess-other",
                created_at=t1,
            ),
        ]
    )
    filtered = _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset({"sess-other"}))
    assert filtered == []


def test_filter_main_timeline_drops_unanswered_human_only_turns():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h-fail", t0, row_id=1, content="test hitl"),
            _human("h-ok", t1, row_id=2, content="hello"),
            _ai("a-ok", "h-ok", row_id=3, created_at=t1, session_id="sess-open"),
        ]
    )
    filtered = _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset())
    assert [m.message_id for m in filtered] == ["h-ok", "a-ok"]


def test_filter_one_human_two_agents_keeps_human_and_own_ai_only():
    """One human → multiple agent runs: filter is scoped per ``agent_id``."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1),
            ThreadMainMessageDomain(
                id=2,
                message_id="a-agent-10",
                thread_id="t1",
                type="ai",
                content="from 10",
                timestamp=t1,
                agent_id=10,
                trigger_message_id="h1",
                invoke_index=0,
                session_id="sess-10",
                created_at=t1,
            ),
            ThreadMainMessageDomain(
                id=3,
                message_id="a-agent-20",
                thread_id="t1",
                type="ai",
                content="from 20",
                timestamp=t2,
                agent_id=20,
                trigger_message_id="h1",
                invoke_index=1,
                session_id="sess-20",
                created_at=t2,
            ),
        ]
    )
    filtered = _filter_and_assert_pairs(rows, agent_id=10, covered=frozenset())
    assert [m.message_id for m in filtered] == ["h1", "a-agent-10"]


def test_filter_same_agent_two_invokes_on_one_human_keeps_both_when_open():
    """One human → two runs for the same agent (invoke 0/1): both AIs stay when uncovered."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1),
            _ai("a0", "h1", row_id=2, invoke_index=0, created_at=t1, session_id="sess-0"),
            _ai("a1", "h1", row_id=3, invoke_index=1, created_at=t2, session_id="sess-1"),
        ]
    )
    filtered = _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset())
    assert [m.message_id for m in filtered] == ["h1", "a0", "a1"]


def test_filter_sequential_humans_same_agent_keeps_independent_turns():
    """Different humans triggering the same agent leave two intact turns on the thread."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 0, 3, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1),
            _ai("a1", "h1", row_id=2, created_at=t1, session_id="sess-1"),
            _human("h2", t2, row_id=3),
            _ai("a2", "h2", row_id=4, created_at=t3, session_id="sess-2"),
        ]
    )
    filtered = _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset())
    assert [m.message_id for m in filtered] == ["h1", "a1", "h2", "a2"]


def test_filter_main_timeline_mixed_covered_and_open_turns():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 0, 3, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h-old", t0, row_id=1),
            _ai("a-old", "h-old", row_id=2, created_at=t1, session_id="sess-covered"),
            _human("h-new", t2, row_id=3),
            _ai("a-new", "h-new", row_id=4, created_at=t3, session_id="sess-open"),
        ]
    )
    filtered = _filter_and_assert_pairs(rows, agent_id=1, covered=frozenset({"sess-covered"}))
    assert [m.message_id for m in filtered] == ["h-new", "a-new"]


def test_slice_main_timeline_turns_keeps_last_k_full_turns():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 0, 3, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1, content="offer"),
            _ai("a1", "h1", row_id=2, created_at=t1),
            _human("h2", t2, row_id=3, content="sure"),
        ]
    )
    sliced = slice_main_timeline_turns(rows, agent_id=1, turn_limit=1)
    assert [m.message_id for m in sliced] == ["h1", "a1"]

    sliced_two = slice_main_timeline_turns(rows, agent_id=1, turn_limit=2)
    assert [m.message_id for m in sliced_two] == ["h1", "a1"]


def test_slice_main_timeline_turn_limit_one_includes_promoted_ai_with_human():
    """turn_limit=1 must not drop the AI attached to the kept human turn."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    rows = sort_timeline_trigger_anchored(
        [
            _human("h1", t0, row_id=1, content="offer"),
            _ai("a1", "h1", row_id=2, created_at=t1),
        ]
    )
    sliced = slice_main_timeline_turns(rows, agent_id=1, turn_limit=1)
    assert [m.message_id for m in sliced] == ["h1", "a1"]


def test_drop_run_rows_duplicating_promoted_main():
    from unittest.mock import MagicMock

    promoted_id = "ai-final"
    keep = MagicMock(type="tool", message_id="tool-1")
    drop = MagicMock(type="ai", message_id=promoted_id)
    out = drop_run_rows_duplicating_promoted_main([keep, drop], promoted_main_message_id=promoted_id)
    assert out == [keep]


@pytest.mark.asyncio
async def test_send_human_zero_runs():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(message_count=0))
    service = ThreadRunService(db, tenant_id=1)
    service.main_repo.insert_human = AsyncMock(
        return_value=ThreadMainMessageDomain(
            id=1,
            message_id="m1",
            thread_id="t1",
            type="human",
            content="hello",
            timestamp=datetime.now(UTC),
        )
    )
    service.run_repo.create_run = AsyncMock()

    message_id, runs = await service.send_human_and_create_runs(
        thread_id="t1",
        content="hello",
        agent_ids=[],
    )
    assert message_id
    assert runs == []
    service.run_repo.create_run.assert_not_called()


@pytest.mark.asyncio
async def test_send_human_two_runs_distinct_invoke_index():
    db = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(message_count=0))
    service = ThreadRunService(db, tenant_id=1)
    service.main_repo.insert_human = AsyncMock(
        return_value=ThreadMainMessageDomain(
            id=1,
            message_id="m1",
            thread_id="t1",
            type="human",
            content="hello",
            timestamp=datetime.now(UTC),
        )
    )

    async def _create_run(**kwargs):
        from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain

        return AgentRunDomain(
            id=str(uuid4()),
            tenant_id=kwargs["tenant_id"],
            thread_id=kwargs["thread_id"],
            agent_id=kwargs["agent_id"],
            trigger_message_id=kwargs["trigger_message_id"],
            invoke_index=kwargs["invoke_index"],
            status=AgentRunStatus.QUEUED,
            session_id=kwargs["session_id"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    service.run_repo.create_run = AsyncMock(side_effect=_create_run)

    _, runs = await service.send_human_and_create_runs(
        thread_id="t1",
        content="hello",
        agent_ids=[10, 20],
    )
    assert len(runs) == 2
    assert runs[0].invoke_index == 0
    assert runs[1].invoke_index == 1
    assert runs[0].trigger_message_id == runs[1].trigger_message_id


def test_run_status_allows_session_summary():
    assert run_status_allows_session_summary(AgentRunStatus.COMPLETED) is True
    assert run_status_allows_session_summary(AgentRunStatus.FAILED) is True
    assert run_status_allows_session_summary(AgentRunStatus.AWAITING_HITL) is False
    assert run_status_allows_session_summary(AgentRunStatus.RUNNING) is False


def test_find_promotable_final_ai_row_skips_tool_call_ai():
    from apps.tenant_app_service.chat.agent_run_domain import find_promotable_final_ai_row

    tool_ai = MagicMock(type="ai", message_id="a1", tool_calls=[{"id": "1"}])
    final_ai = MagicMock(type="ai", message_id="a2", tool_calls=None)
    assert find_promotable_final_ai_row([tool_ai, final_ai]) is final_ai
    assert find_promotable_final_ai_row([tool_ai]) is None


@pytest.mark.asyncio
async def test_finalize_run_for_main_promotes_and_completes():
    from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain, AgentRunStatus

    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=1)
    run_id = "run-1"
    now = datetime.now(UTC)
    run = AgentRunDomain(
        id=run_id,
        tenant_id=1,
        thread_id="t1",
        agent_id=9,
        trigger_message_id="h1",
        invoke_index=0,
        status=AgentRunStatus.RUNNING,
        session_id="s1",
        created_at=now,
        updated_at=now,
    )
    service.run_repo.get_run = AsyncMock(return_value=run)
    service.main_repo.get_promoted_ai_for_run = AsyncMock(return_value=None)
    ai_row = MagicMock(type="ai", message_id="ai-1", tool_calls=None)
    service.run_message_repo.list_for_run = AsyncMock(return_value=[ai_row])
    with patch(
        "apps.tenant_app_service.agents.message_persistence_adapters.agent_run_message_to_langchain",
        return_value=AIMessage(id="ai-1", content="hello"),
    ):
        service.promote_final_ai = AsyncMock()
        service.mark_run_completed = AsyncMock()
        await service.finalize_run_for_main(run_id)

    service.promote_final_ai.assert_awaited_once()
    service.mark_run_completed.assert_awaited_once_with(run_id)


@pytest.mark.asyncio
async def test_finalize_run_for_main_skips_awaiting_hitl():
    from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain, AgentRunStatus

    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=1)
    run = AgentRunDomain(
        id="run-1",
        tenant_id=1,
        thread_id="t1",
        agent_id=9,
        trigger_message_id="h1",
        invoke_index=0,
        status=AgentRunStatus.AWAITING_HITL,
        session_id="s1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.run_repo.get_run = AsyncMock(return_value=run)
    service.promote_final_ai = AsyncMock()
    service.mark_run_completed = AsyncMock()
    await service.finalize_run_for_main("run-1")
    service.promote_final_ai.assert_not_awaited()
    service.mark_run_completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_promote_idempotent():
    db = AsyncMock()
    service = ThreadRunService(db, tenant_id=1)
    existing = ThreadMainMessageDomain(
        id=2,
        message_id="ai1",
        thread_id="t1",
        type="ai",
        content="done",
        timestamp=datetime.now(UTC),
        agent_run_id="run-1",
    )
    service.main_repo.get_promoted_ai_for_run = AsyncMock(return_value=existing)
    service.main_repo.insert_promoted_ai = AsyncMock()

    from langchain_core.messages import AIMessage

    result = await service.promote_final_ai(
        run_id="run-1",
        thread_id="t1",
        agent_id=1,
        trigger_message_id="h1",
        invoke_index=0,
        session_id="s1",
        final_message=AIMessage(content="done"),
    )
    assert result == existing
    service.main_repo.insert_promoted_ai.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_skips_legacy_human_persist_for_normal_send():
    from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    request = ChatRequest(
        tenant_id=1,
        agent_id=1,
        message=SimpleMessage(role="human", content="hello"),
        thread_id="thread-1",
    )
    user = MagicMock(id=1, tenant_id=1, tenant_name="t")
    db = AsyncMock()

    service = ChatTurnService(1, db)
    service._resolve_agent_id = AsyncMock(return_value=1)
    service._cancel_superseded_hitl_if_needed = AsyncMock()
    service._get_agent_graph = AsyncMock(return_value=(MagicMock(get_name=MagicMock(return_value="Agent")), None))
    service._convert_to_langchain_messages = MagicMock(return_value=[])
    service._inject_message_attachments = AsyncMock(return_value=[])
    service.get_tenant_domain = AsyncMock(return_value=MagicMock(config=MagicMock(to_dict=MagicMock(return_value={}))))
    service._build_runtime_config = MagicMock(return_value={"configurable": {"thread_id": "thread-1"}})
    service.create_thread_title_if_1st_message = AsyncMock(return_value=None)
    service._reconcile_active_runs_before_new_turn = AsyncMock()

    with patch("apps.tenant_app_service.chat.turn_service.guard_thread_turn_start", AsyncMock()):
        with patch.object(ThreadRunService, "send_human_and_create_runs", AsyncMock()) as send_mock:
            from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain

            send_mock.return_value = (
                "human-1",
                [
                    AgentRunDomain(
                        id="run-1",
                        tenant_id=1,
                        thread_id="thread-1",
                        agent_id=1,
                        trigger_message_id="human-1",
                        invoke_index=0,
                        status=AgentRunStatus.QUEUED,
                        session_id="sess-1",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                ],
            )
            prepared = await service.prepare_chat_turn(request, user)

    assert prepared.run_id == "run-1"
    assert prepared.trigger_message_id == "human-1"


@pytest.mark.asyncio
async def test_get_tool_call_detail_returns_none_when_run_store_misses():
    from apps.tenant_app_service.chat.thread_service import ThreadService

    db = AsyncMock()
    service = ThreadService(tenant_id=1, db=db)

    with patch(
        "apps.tenant_app_service.chat.agent_run_repository.AgentRunRepository.get_by_session_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch(
            "apps.tenant_app_service.chat.agent_run_message_repository.AgentRunMessageRepository.get_tool_message_by_call_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await service.get_tool_call_detail(
                thread_id="thread-1",
                tool_call_id="call_abc",
                session_id="sess-1",
            )

    assert result is None


@pytest.mark.asyncio
async def test_get_tool_call_detail_retries_run_lookup_without_run_id():
    from apps.tenant_app_service.chat.thread_service import ThreadService

    db = AsyncMock()
    service = ThreadService(tenant_id=1, db=db)
    run = MagicMock()
    run.id = "run-wrong"
    run_row = MagicMock()
    run_row.additional_kwargs = {"tool_call_id": "call_xyz"}

    with patch(
        "apps.tenant_app_service.chat.agent_run_repository.AgentRunRepository.get_by_session_id",
        new_callable=AsyncMock,
        return_value=run,
    ):
        with patch(
            "apps.tenant_app_service.chat.agent_run_message_repository.AgentRunMessageRepository.get_tool_message_by_call_id",
            new_callable=AsyncMock,
            side_effect=[None, run_row],
        ) as get_tool:
            with patch(
                "apps.tenant_app_service.agents.message_persistence_adapters.agent_run_message_to_chat_message",
                return_value=MagicMock(),
            ):
                with patch(
                    "apps.tenant_app_service.chat.thread_service.chat_message_to_domain",
                    return_value=MagicMock(),
                ):
                    with patch(
                        "apps.tenant_app_service.chat.thread_service.domain_message_to_api",
                        return_value=MagicMock(role="tool"),
                    ):
                        result = await service.get_tool_call_detail(
                            thread_id="thread-1",
                            tool_call_id="call_xyz",
                            session_id="sess-1",
                        )

    assert result is not None
    assert get_tool.await_count == 2
    get_tool.assert_any_await("thread-1", "call_xyz", run_id="run-wrong")
    get_tool.assert_any_await("thread-1", "call_xyz", run_id=None)
