"""Unit tests for ConversationMemoryManager.

All repository and database dependencies are mocked with AsyncMock/MagicMock.
No database (SQLite or Postgres) is touched in this file.

What is tested here:
  - Assembly logic of load_messages_with_summary (output order, limits, filtering)
  - _ensure_hitl_context_run injection logic
  - add_messages preprocessing (filter SystemMessages, dedup, field mapping)

What is NOT tested here (belongs in integration tests):
  - Actual SQL queries (is_summarized filter, JSON tool_calls, ordering by created_at)
  - Full save→load round-trip persistence
  - PostgreSQL-specific JSON behaviour
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.db.models import ChatMessage
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager
from apps.tenant_app_service.chat.agent_run_domain import (
    ThreadMainMessageDomain,
    filter_main_timeline_for_context_load,
    sort_timeline_trigger_anchored,
)
from tests.unit.chat.main_timeline_pair_assertions import assert_main_timeline_summary_pairs_consistent

# ─── Constants ────────────────────────────────────────────────────────────────

THREAD_ID = "thread-unit-1"
AGENT_ID = 456
TENANT_ID = 1
_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)

_TSR_PATH = "apps.tenant_app_service.chat.thread_summary_repository.ThreadSummaryRepository"
_SSR_PATH = "apps.tenant_app_service.chat.session_summary_repository.SessionSummaryRepository"
_RUN_MR_PATH = "apps.tenant_app_service.chat.agent_run_message_repository.AgentRunMessageRepository"
_MAIN_MR_PATH = "apps.tenant_app_service.chat.main_message_repository.MainMessageRepository"
_AGENT_RUN_REPO_PATH = "apps.tenant_app_service.chat.agent_run_repository.AgentRunRepository"
RUN_ID = "run-unit-1"
TRIGGER_MSG_ID = "trigger-human-1"
_HITL_BLOCKING_PATH = "apps.tenant_app_service.hitl.history.is_hitl_proposal_blocking"

# ─── Builders ─────────────────────────────────────────────────────────────────


def _db_msg(
    db_id: int,
    msg_id: str,
    msg_type: str,
    content: str,
    *,
    tool_calls=None,
    additional_kwargs=None,
    session_id: str = "session-1",
) -> MagicMock:
    """Build a minimal ChatMessage mock consumable by _db_message_to_langchain."""
    m = MagicMock(spec=ChatMessage)
    m.id = db_id
    m.message_id = msg_id
    m.type = msg_type
    m.content = content
    m.tool_calls = tool_calls
    m.additional_kwargs = additional_kwargs or {}
    m.session_id = session_id
    m.message_metadata = None  # suppresses timestamp-injection branch
    m.timestamp = _T0
    m.created_at = _T0
    return m


def _thread_summary(version: int, content: str) -> MagicMock:
    ts = MagicMock()
    ts.version = version
    ts.summary_content = content
    ts.session_range = {}
    ts.message_range = {}
    return ts


def _main_domain(
    msg_id: str,
    msg_type: str,
    content: str,
    *,
    session_id: str | None = None,
    agent_id: int = AGENT_ID,
    row_id: int = 1,
    trigger_message_id: str | None = None,
) -> ThreadMainMessageDomain:
    return ThreadMainMessageDomain(
        id=row_id,
        message_id=msg_id,
        thread_id=THREAD_ID,
        type=msg_type,
        content=content,
        timestamp=_T0,
        agent_id=agent_id,
        session_id=session_id,
        trigger_message_id=trigger_message_id,
        created_at=_T0,
    )


def _assert_loaded_main_pairs_consistent(
    main_rows: list[ThreadMainMessageDomain],
    *,
    covered_session_ids: frozenset[str],
) -> None:
    ordered = sort_timeline_trigger_anchored(main_rows)
    filtered = filter_main_timeline_for_context_load(
        ordered,
        agent_id=AGENT_ID,
        covered_session_ids=covered_session_ids,
    )
    assert_main_timeline_summary_pairs_consistent(
        ordered,
        filtered,
        agent_id=AGENT_ID,
        covered_session_ids=covered_session_ids,
    )


def _session_summary(text: str, session_id: str = "session-summary-1") -> MagicMock:
    ss = MagicMock()
    ss.summary_text = text
    ss.session_id = session_id
    return ss


def _make_manager(*, trigger_message_id: str | None = None) -> tuple:
    """Return (manager, db_mock, run_repo_mock, main_repo_mock) with run stores patched."""
    db_mock = AsyncMock()
    thread_mock = MagicMock()
    thread_mock.message_count = 0
    db_mock.get.return_value = thread_mock

    with (
        patch(_RUN_MR_PATH) as MockRunMR,
        patch(_MAIN_MR_PATH) as MockMainMR,
        patch(_TSR_PATH) as MockTSR,
        patch(_SSR_PATH) as MockSSR,
        patch(_AGENT_RUN_REPO_PATH) as MockAgentRunRepo,
    ):
        run_repo_mock = AsyncMock()
        run_repo_mock.get_tool_message_by_call_id.return_value = None
        run_repo_mock.has_ai_message_after_db_id_in_session.return_value = False
        MockRunMR.return_value = run_repo_mock
        main_repo_mock = AsyncMock()
        main_repo_mock.list_for_thread.return_value = []
        main_repo_mock.get_promoted_ai_for_run.return_value = None
        MockMainMR.return_value = main_repo_mock
        thread_summary_repo_mock = AsyncMock()
        thread_summary_repo_mock.get_recent_summaries.return_value = []
        MockTSR.return_value = thread_summary_repo_mock
        session_summary_repo_mock = AsyncMock()
        session_summary_repo_mock.get_unsummarized_sessions.return_value = []
        session_summary_repo_mock.list_session_ids_in_thread_summary.return_value = []
        MockSSR.return_value = session_summary_repo_mock
        agent_run_repo_mock = AsyncMock()
        if trigger_message_id is not None:
            run_domain = MagicMock()
            run_domain.trigger_message_id = trigger_message_id
            agent_run_repo_mock.get_run = AsyncMock(return_value=run_domain)
        else:
            agent_run_repo_mock.get_run = AsyncMock(return_value=None)
        MockAgentRunRepo.return_value = agent_run_repo_mock
        mgr = ConversationMemoryManager(
            db_mock,
            THREAD_ID,
            tenant_id=TENANT_ID,
            agent_id=AGENT_ID,
            run_id=RUN_ID,
        )

    return mgr, db_mock, run_repo_mock


async def _load(
    mgr,
    repo_mock,
    *,
    thread_summaries=None,
    session_summaries=None,
    unsummarized_msgs=None,
    last_ai_tool=None,
    tail_msgs=None,
    thread_summary_limit: int = 1,
    session_summary_limit: int = 2,
    main_timeline_turn_limit: int | None = None,
    run_message_limit: int | None = None,
):
    """Wire mock return values and invoke load_messages_with_summary."""
    repo_mock.get_unsummarized_messages.return_value = list(unsummarized_msgs or [])
    repo_mock.get_last_ai_message_with_tool_calls.return_value = last_ai_tool
    repo_mock.get_messages_from_db_id.return_value = list(tail_msgs or [])

    mgr.thread_summary_repo.get_recent_summaries.return_value = list(thread_summaries or [])
    mgr.session_summary_repo.get_unsummarized_sessions.return_value = list(session_summaries or [])

    return await mgr.load_messages_with_summary(
        thread_summary_limit=thread_summary_limit,
        session_summary_limit=session_summary_limit,
        main_timeline_turn_limit=main_timeline_turn_limit,
        run_message_limit=run_message_limit,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TestAssemblyLogic
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAssemblyLogic:
    """Verify load_messages_with_summary output structure and ordering."""

    async def test_thread_not_found_returns_empty(self):
        mgr, db_mock, repo_mock = _make_manager()
        db_mock.get.return_value = None

        result = await _load(mgr, repo_mock)

        assert result == []

    async def test_load_emits_context_load_manifest(self, caplog):
        import logging

        mgr, _, repo_mock = _make_manager()
        with caplog.at_level(logging.INFO):
            await _load(
                mgr,
                repo_mock,
                unsummarized_msgs=[_db_msg(1, "m1", "human", "Hi")],
                main_timeline_turn_limit=4,
                run_message_limit=None,
            )
        assert any("context_load_manifest" in record.message for record in caplog.records)

    async def test_output_order_thread_summary_then_session_then_messages(self):
        """[ThreadSummary SystemMsg] → [SessionSummary SystemMsg] → [messages]."""
        mgr, _, repo_mock = _make_manager()

        msg_a = _db_msg(1, "m1", "human", "Hello")
        msg_b = _db_msg(2, "m2", "ai", "Hi")

        loaded = await _load(
            mgr,
            repo_mock,
            thread_summaries=[_thread_summary(1, "Thread context")],
            session_summaries=[_session_summary("Session context")],
            unsummarized_msgs=[msg_b, msg_a],  # DESC from repo → reversed to ASC
        )

        assert len(loaded) == 4
        assert isinstance(loaded[0], SystemMessage)
        assert loaded[0].additional_kwargs["summary_type"] == "thread_summary"
        assert "Thread context" in loaded[0].content

        assert isinstance(loaded[1], SystemMessage)
        assert loaded[1].additional_kwargs["summary_type"] == "session_summary"
        assert "Session context" in loaded[1].content

        assert loaded[2].content == "Hello"
        assert loaded[3].content == "Hi"

    async def test_thread_summary_limit_zero_omits_thread_system_message(self):
        mgr, _, repo_mock = _make_manager()

        loaded = await _load(
            mgr,
            repo_mock,
            thread_summaries=[_thread_summary(1, "Should not appear")],
            thread_summary_limit=0,
        )

        assert not any(
            isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "thread_summary" for m in loaded
        )

    async def test_session_summary_limit_zero_omits_session_system_message(self):
        mgr, _, repo_mock = _make_manager()

        loaded = await _load(
            mgr,
            repo_mock,
            session_summaries=[_session_summary("Should not appear")],
            session_summary_limit=0,
        )

        assert not any(
            isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "session_summary"
            for m in loaded
        )

    async def test_session_summary_limit_caps_to_most_recent(self):
        """3 unsummarized sessions + limit=1 → only newest appears."""
        mgr, _, repo_mock = _make_manager()

        # ASC order (oldest first) as returned by get_unsummarized_sessions
        sessions = [
            _session_summary("Old session"),
            _session_summary("Middle session"),
            _session_summary("New session"),
        ]

        loaded = await _load(mgr, repo_mock, session_summaries=sessions, session_summary_limit=1)

        session_sys = [
            m
            for m in loaded
            if isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "session_summary"
        ]
        assert len(session_sys) == 1
        assert "New session" in session_sys[0].content
        assert "Old session" not in session_sys[0].content

    async def test_all_unsummarized_sessions_shown_within_limit(self):
        """2 sessions, limit=5 → both appear in the single SystemMessage."""
        mgr, _, repo_mock = _make_manager()

        loaded = await _load(
            mgr,
            repo_mock,
            session_summaries=[_session_summary("S1"), _session_summary("S2")],
            session_summary_limit=5,
        )

        session_sys = [
            m
            for m in loaded
            if isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "session_summary"
        ]
        assert len(session_sys) == 1
        assert "S1" in session_sys[0].content
        assert "S2" in session_sys[0].content

    async def test_run_message_limit_zero_passes_zero_to_repo(self):
        """run_message_limit=0 means load zero unsummarized run messages."""
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, run_message_limit=0)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            run_id=RUN_ID,
            agent_id=AGENT_ID,
            limit=0,
        )

    async def test_run_message_limit_none_passes_none_to_repo(self):
        """run_message_limit=None means no cap (load all unsummarized run messages)."""
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, run_message_limit=None)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            run_id=RUN_ID,
            agent_id=AGENT_ID,
            limit=None,
        )

    async def test_run_message_limit_n_passes_n_to_repo(self):
        """run_message_limit=5 → repo receives limit=5."""
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, run_message_limit=5)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            run_id=RUN_ID,
            agent_id=AGENT_ID,
            limit=5,
        )

    async def test_run_message_limit_none_loads_full_run(self):
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, run_message_limit=None)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            run_id=RUN_ID,
            agent_id=AGENT_ID,
            limit=None,
        )

    async def test_run_message_limit_zero_skips_run_rows(self):
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, main_timeline_turn_limit=3, run_message_limit=0)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            run_id=RUN_ID,
            agent_id=AGENT_ID,
            limit=0,
        )

    async def test_desc_messages_reversed_to_chronological_in_output(self):
        """Repo returns newer-first (DESC); manager must reverse to ASC for LLM context."""
        mgr, _, repo_mock = _make_manager()

        msg_a = _db_msg(10, "a", "human", "First")
        msg_b = _db_msg(20, "b", "human", "Second")

        loaded = await _load(mgr, repo_mock, unsummarized_msgs=[msg_b, msg_a])

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert conv[0].content == "First"
        assert conv[1].content == "Second"

    async def test_multiple_thread_summaries_coalesced_into_one_system_message(self):
        """Multiple thread summaries → single SystemMessage with summary_count metadata."""
        mgr, _, repo_mock = _make_manager()

        loaded = await _load(
            mgr,
            repo_mock,
            thread_summaries=[_thread_summary(1, "v1"), _thread_summary(2, "v2")],
            thread_summary_limit=2,
        )

        thread_sys = [
            m
            for m in loaded
            if isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "thread_summary"
        ]
        assert len(thread_sys) == 1
        assert thread_sys[0].additional_kwargs["summary_count"] == 2
        assert "v1" in thread_sys[0].content
        assert "v2" in thread_sys[0].content

    async def test_no_sources_returns_empty_list(self):
        mgr, _, repo_mock = _make_manager()
        loaded = await _load(mgr, repo_mock, thread_summary_limit=0, session_summary_limit=0)
        assert loaded == []

    async def test_legacy_main_ai_without_trigger_drops_human_when_session_summarized(self):
        """End-to-end load must not leave orphan human when legacy AI lacks trigger_message_id."""
        mgr, _, repo_mock = _make_manager(trigger_message_id="h-current")
        sid = "session-covered-legacy"
        main_rows = [
            _main_domain("h-old", "human", "Old question", row_id=1),
            _main_domain(
                "a-old",
                "ai",
                "Old answer",
                session_id=sid,
                row_id=2,
                trigger_message_id=None,
            ),
        ]
        _assert_loaded_main_pairs_consistent(main_rows, covered_session_ids=frozenset({sid}))
        mgr.main_message_repo.list_for_thread.return_value = main_rows
        mgr.main_message_repo.get_by_message_id.return_value = _main_domain(
            "h-current", "human", "Current line", row_id=3
        )
        repo_mock.get_unsummarized_messages.return_value = []

        loaded = await _load(
            mgr,
            repo_mock,
            session_summaries=[_session_summary("Recap", session_id=sid)],
            thread_summary_limit=0,
        )

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert [m.content for m in conv] == ["Current line"]

    async def test_main_promoted_ai_omitted_when_session_has_summary(self):
        """Covered session drops history pair; current trigger human appended once."""
        mgr, _, repo_mock = _make_manager(trigger_message_id="h1")
        sid = "session-covered-1"
        mgr.main_message_repo.list_for_thread.return_value = [
            _main_domain("h1", "human", "Question"),
            _main_domain("a1", "ai", "Answer", session_id=sid, row_id=2, trigger_message_id="h1"),
        ]
        mgr.main_message_repo.get_by_message_id.return_value = _main_domain("h1", "human", "Question")

        loaded = await _load(
            mgr,
            repo_mock,
            session_summaries=[_session_summary("Session recap", session_id=sid)],
            thread_summary_limit=0,
        )

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert len(conv) == 1
        assert conv[0].content == "Question"

    async def test_main_ai_omitted_when_session_in_thread_summary_rollup(self):
        mgr, _, repo_mock = _make_manager(trigger_message_id="h1")
        sid = "session-in-thread-summary"
        mgr.main_message_repo.list_for_thread.return_value = [
            _main_domain("h1", "human", "Old question"),
            _main_domain("a1", "ai", "Old answer", session_id=sid, row_id=2),
        ]
        mgr.main_message_repo.get_by_message_id.return_value = _main_domain("h1", "human", "Old question")

        mgr.thread_summary_repo.get_recent_summaries.return_value = [_thread_summary(1, "Long thread recap")]
        mgr.session_summary_repo.get_unsummarized_sessions.return_value = []
        mgr.session_summary_repo.list_session_ids_in_thread_summary.return_value = [sid]
        repo_mock.get_unsummarized_messages.return_value = []

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=1,
            session_summary_limit=0,
        )

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert len(conv) == 1
        assert conv[0].content == "Old question"

    async def test_active_run_sees_prior_turns_not_current_human_on_main(self):
        """Concurrent-style thread: run on h2 loads h1 turn on main, h2 only via append."""
        mgr, _, repo_mock = _make_manager(trigger_message_id="h2")
        mgr.main_message_repo.list_for_thread.return_value = [
            _main_domain("h1", "human", "First ask", row_id=1),
            _main_domain(
                "a1",
                "ai",
                "First reply",
                session_id="sess-1",
                row_id=2,
                trigger_message_id="h1",
            ),
            _main_domain("h2", "human", "Second ask", row_id=3),
        ]
        mgr.main_message_repo.get_by_message_id.return_value = _main_domain(
            "h2", "human", "Second ask", row_id=3
        )
        repo_mock.get_unsummarized_messages.return_value = []

        loaded = await _load(mgr, repo_mock, thread_summary_limit=0, session_summary_limit=0)

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert [m.content for m in conv] == ["First ask", "First reply", "Second ask"]

    async def test_trigger_human_appended_after_main_before_run_messages(self):
        mgr, _, repo_mock = _make_manager(trigger_message_id="h-current")
        mgr.main_message_repo.list_for_thread.return_value = [
            _main_domain("h-old", "human", "Past"),
            _main_domain("a-old", "ai", "Past reply", session_id="sess-open", row_id=2),
        ]
        mgr.main_message_repo.get_by_message_id.return_value = _main_domain(
            "h-current", "human", "Current user line"
        )
        msg_run = _db_msg(1, "m-run", "ai", "Working")

        loaded = await _load(mgr, repo_mock, unsummarized_msgs=[msg_run])

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert [m.content for m in conv] == ["Past", "Past reply", "Current user line", "Working"]

    async def test_run_ai_omitted_when_duplicates_promoted_main(self):
        """Promoted main AI should not appear again from agent_run_messages."""
        mgr, _, repo_mock = _make_manager()
        mgr.main_message_repo.list_for_thread.return_value = [
            _main_domain("h1", "human", "Question"),
            _main_domain("a1", "ai", "Final answer", session_id="sess-1", row_id=2),
        ]
        mgr.main_message_repo.get_promoted_ai_for_run.return_value = _main_domain(
            "a1", "ai", "Final answer", session_id="sess-1", row_id=2
        )
        run_ai = _db_msg(1, "a1", "ai", "Final answer", session_id="sess-1")

        loaded = await _load(
            mgr,
            repo_mock,
            unsummarized_msgs=[run_ai],
            thread_summary_limit=0,
            session_summary_limit=0,
        )

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert len(conv) == 2
        assert conv[0].content == "Question"
        assert conv[1].content == "Final answer"


# ─────────────────────────────────────────────────────────────────────────────
# TestEnsureHitlContext
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEnsureHitlContext:
    """Verify _ensure_hitl_context_run injection logic in isolation."""

    async def test_no_last_ai_returns_messages_unchanged(self):
        """get_last_ai_message_with_tool_calls returns None → list untouched."""
        mgr, _, repo_mock = _make_manager()
        repo_mock.get_last_ai_message_with_tool_calls.return_value = None

        msgs = [_db_msg(1, "m1", "human", "Q"), _db_msg(2, "m2", "ai", "A")]
        result, injected = await mgr._ensure_hitl_context_run(msgs)

        assert result is msgs
        assert injected == 0
        repo_mock.get_messages_from_db_id.assert_not_called()

    async def test_anchor_already_in_loaded_messages_returns_unchanged(self):
        """Anchor present in loaded set → no injection, no extra DB call."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI with tool", tool_calls=[{"id": "tc1"}])
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor

        msgs = [anchor, _db_msg(20, "tool-1", "tool", "Result")]
        result, injected = await mgr._ensure_hitl_context_run(msgs)

        assert result is msgs
        assert injected == 0
        repo_mock.get_messages_from_db_id.assert_not_called()

    async def test_anchor_missing_injects_tail_in_correct_order(self):
        """Anchor cut off → get_messages_from_db_id fetches tail and merges in ASC order."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI with tool", tool_calls=[{"id": "tc1"}])
        tool_msg = _db_msg(20, "tool-1", "tool", "Result")
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_messages_from_db_id.return_value = [anchor, tool_msg]

        later_q = _db_msg(30, "h-1", "human", "Follow-up")
        result, injected = await mgr._ensure_hitl_context_run([later_q])

        repo_mock.get_messages_from_db_id.assert_called_once_with(
            run_id=RUN_ID,
            agent_id=AGENT_ID,
            from_db_id=10,
        )
        assert len(result) == 3
        assert [m.id for m in result] == [10, 20, 30]
        assert injected == 2

    async def test_tail_deduplicates_overlap_with_loaded(self):
        """Tail items already in loaded_msgs are not duplicated."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        tool_msg = _db_msg(20, "tool-1", "tool", "Result")
        later_q = _db_msg(30, "h-1", "human", "Q")

        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_messages_from_db_id.return_value = [anchor, tool_msg, later_q]

        # later_q is already in loaded; should appear only once
        result, injected = await mgr._ensure_hitl_context_run([later_q])

        assert len(result) == 3
        assert [m.id for m in result] == [10, 20, 30]
        assert injected == 2

    async def test_empty_tail_returns_original_list(self):
        """get_messages_from_db_id returns [] (unexpected) → original list returned."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_messages_from_db_id.return_value = []

        later_q = _db_msg(30, "h-1", "human", "Q")
        result, injected = await mgr._ensure_hitl_context_run([later_q])

        assert result == [later_q]
        assert injected == 0

    async def test_resolved_chain_skips_injection(self):
        """Completed AI→Tool→AI chains are not re-injected for HITL continuity."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI with tool", tool_calls=[{"id": "tc1"}])
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(20, "tool-1", "tool", "Result")
        repo_mock.has_ai_message_after_db_id_in_session.return_value = True

        later_q = _db_msg(40, "h-1", "human", "Follow-up")
        result, injected = await mgr._ensure_hitl_context_run([later_q])

        assert result == [later_q]
        assert injected == 0
        repo_mock.get_messages_from_db_id.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# TestIsToolChainResolved
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestIsToolChainResolved:
    """Verify _is_tool_chain_resolved orchestrates repo lookups and domain rules."""

    async def test_resolved_when_all_tools_answered_and_final_ai_exists(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(20, "tool-1", "tool", "Result")
        repo_mock.has_ai_message_after_db_id_in_session.return_value = True

        assert await mgr._is_tool_chain_resolved(anchor) is True

        repo_mock.get_tool_message_by_call_id.assert_called_once_with(THREAD_ID, "tc1", run_id=RUN_ID)
        repo_mock.has_ai_message_after_db_id_in_session.assert_called_once_with(
            THREAD_ID, AGENT_ID, 20, "session-1"
        )

    async def test_unresolved_when_tool_response_missing(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_tool_message_by_call_id.return_value = None

        assert await mgr._is_tool_chain_resolved(anchor) is False

        repo_mock.has_ai_message_after_db_id_in_session.assert_not_called()

    async def test_unresolved_when_tool_answered_but_no_final_ai(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(20, "tool-1", "tool", "Result")
        repo_mock.has_ai_message_after_db_id_in_session.return_value = False

        assert await mgr._is_tool_chain_resolved(anchor) is False

    async def test_unresolved_when_multiple_tool_calls_partially_fulfilled(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}, {"id": "tc2"}])

        async def get_tool_side_effect(thread_id, tool_call_id, run_id=None):
            if tool_call_id == "tc1":
                return _db_msg(20, "tool-1", "tool", "R1")
            return None

        repo_mock.get_tool_message_by_call_id.side_effect = get_tool_side_effect

        assert await mgr._is_tool_chain_resolved(anchor) is False

        repo_mock.has_ai_message_after_db_id_in_session.assert_not_called()

    async def test_unresolved_when_tool_message_is_hitl_placeholder(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(
            20,
            "tool-1",
            "tool",
            "Skipped: Waiting for HITL approval",
            additional_kwargs={
                "hitl": {"type": "approval_request", "proposal_id": "hitl_pending"},
            },
        )

        with patch(_HITL_BLOCKING_PATH, AsyncMock(return_value=True)):
            assert await mgr._is_tool_chain_resolved(anchor) is False

    async def test_resolved_when_tool_message_is_terminal_hitl_placeholder(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(
            20,
            "tool-1",
            "tool",
            "Tool 'hitl_test_echo' requires human approval.",
            additional_kwargs={
                "hitl": {"type": "approval_request", "proposal_id": "hitl_expired"},
            },
        )

        with patch(_HITL_BLOCKING_PATH, AsyncMock(return_value=False)):
            assert await mgr._is_tool_chain_resolved(anchor) is True

        repo_mock.has_ai_message_after_db_id_in_session.assert_not_called()

    async def test_unresolved_when_pending_hitl_placeholder_blocks_chain(self):
        mgr, _, repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(
            20,
            "tool-1",
            "tool",
            "Tool 'hitl_test_echo' requires human approval.",
            additional_kwargs={
                "hitl": {"type": "approval_request", "proposal_id": "hitl_pending"},
            },
        )

        with patch(_HITL_BLOCKING_PATH, AsyncMock(return_value=True)):
            assert await mgr._is_tool_chain_resolved(anchor) is False

    async def test_unresolved_when_anchor_has_no_session_id(self):
        mgr, _, _repo_mock = _make_manager()
        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}], session_id=None)

        assert await mgr._is_tool_chain_resolved(anchor) is False


# ─────────────────────────────────────────────────────────────────────────────
# TestAddMessages
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAddMessages:
    """Verify add_messages preprocessing, field mapping, and side-effects."""

    def _runnable_config(self) -> RunnableConfig:
        from apps.tenant_app_service.agents.domain import (
            AgentRuntimeContext,
            AgentTenantContext,
            AgentUserContext,
        )

        ctx = AgentRuntimeContext(
            tenant=AgentTenantContext(tenant_id=TENANT_ID, tenant_name="t", config={}),
            user=AgentUserContext(user_id=1, username="u", role="admin", tenant_id=TENANT_ID, tenant_name="t"),
            agent_id=AGENT_ID,
            agent_name="test_agent",
            thread_id=THREAD_ID,
            session_id="sess-123",
        )
        return RunnableConfig(
            configurable={
                "thread_id": THREAD_ID,
                "runtime": ctx.model_dump(),
                "session_id": ctx.session_id,
                "run_id": RUN_ID,
            }
        )

    async def test_empty_list_is_no_op(self):
        mgr, db_mock, repo_mock = _make_manager()
        await mgr.add_messages([], self._runnable_config())

        repo_mock.save_messages_batch.assert_not_called()

    async def test_system_messages_are_filtered_out(self):
        """SystemMessages must never reach save_messages_batch."""
        mgr, _, repo_mock = _make_manager()
        repo_mock.get_messages_by_ids.return_value = []

        await mgr.add_messages(
            [SystemMessage(content="context"), AIMessage(id="ai1", content="Hello")],
            self._runnable_config(),
        )

        saved = repo_mock.save_messages_batch.call_args[0][0]
        assert len(saved) == 1
        assert saved[0].type == "ai"

    async def test_duplicate_message_ids_are_skipped(self):
        """Messages whose IDs already exist in the DB are not re-saved."""
        mgr, _, repo_mock = _make_manager()

        existing = MagicMock()
        existing.message_id = "ai1"
        repo_mock.get_messages_by_ids.return_value = [existing]

        await mgr.add_messages(
            [AIMessage(id="ai1", content="Already saved"), AIMessage(id="ai2", content="New")],
            self._runnable_config(),
        )

        saved = repo_mock.save_messages_batch.call_args[0][0]
        assert len(saved) == 1
        assert saved[0].message_id == "ai2"

    async def test_thread_not_found_skips_save(self):
        """Missing thread → save is aborted, no DB writes."""
        mgr, db_mock, repo_mock = _make_manager()
        # Pre-flush: thread absent for the second get() call (after preprocess)
        repo_mock.get_messages_by_ids.return_value = []
        db_mock.get.side_effect = [None]  # thread not found on first db.get call

        await mgr.add_messages([HumanMessage(id="h1", content="Q")], self._runnable_config())

        repo_mock.save_messages_batch.assert_not_called()

    async def test_tool_call_id_written_into_additional_kwargs(self):
        """ToolMessage.tool_call_id is injected into additional_kwargs for DB storage."""
        mgr, _, repo_mock = _make_manager()
        repo_mock.get_messages_by_ids.return_value = []

        await mgr.add_messages(
            [ToolMessage(id="t1", content="Result", tool_call_id="call_xyz")],
            self._runnable_config(),
        )

        saved = repo_mock.save_messages_batch.call_args[0][0]
        assert saved[0].additional_kwargs.get("tool_call_id") == "call_xyz"

    async def test_ai_tool_calls_stored_in_dedicated_column(self):
        """AIMessage.tool_calls are serialised into the ChatMessage.tool_calls field."""
        mgr, _, repo_mock = _make_manager()
        repo_mock.get_messages_by_ids.return_value = []

        tc = [{"id": "call_1", "name": "my_tool", "args": {"x": 1}, "type": "tool_call"}]
        await mgr.add_messages(
            [AIMessage(id="ai1", content="calling", tool_calls=tc)],
            self._runnable_config(),
        )

        saved = repo_mock.save_messages_batch.call_args[0][0]
        assert saved[0].tool_calls == tc

    async def test_add_messages_does_not_mutate_thread_message_count(self):
        """Run-scoped persistence does not bump legacy thread.message_count."""
        mgr, db_mock, repo_mock = _make_manager()
        repo_mock.get_messages_by_ids.return_value = []
        db_mock.get.return_value.message_count = 3

        await mgr.add_messages(
            [HumanMessage(id="h1", content="A"), HumanMessage(id="h2", content="B")],
            self._runnable_config(),
        )

        assert db_mock.get.return_value.message_count == 3
