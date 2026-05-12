"""Unit tests for ConversationMemoryManager.

All repository and database dependencies are mocked with AsyncMock/MagicMock.
No database (SQLite or Postgres) is touched in this file.

What is tested here:
  - Assembly logic of load_messages_with_summary (output order, limits, filtering)
  - _ensure_hitl_context injection logic
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

# ─── Constants ────────────────────────────────────────────────────────────────

THREAD_ID = "thread-unit-1"
AGENT_ID = 456
TENANT_ID = 1
_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)

_TSR_PATH = "apps.tenant_app_service.chat.thread_summary_repository.ThreadSummaryRepository"
_SSR_PATH = "apps.tenant_app_service.chat.session_summary_repository.SessionSummaryRepository"
_MR_PATH = "apps.tenant_app_service.chat.message_repository.MessageRepository"
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


def _session_summary(text: str) -> MagicMock:
    ss = MagicMock()
    ss.summary_text = text
    return ss


def _make_manager() -> tuple:
    """Return (manager, db_mock, repo_mock) with MessageRepository patched."""
    db_mock = AsyncMock()
    thread_mock = MagicMock()
    thread_mock.message_count = 0
    db_mock.get.return_value = thread_mock

    with patch(_MR_PATH) as MockMR:
        repo_mock = AsyncMock()
        repo_mock.get_tool_message_by_call_id.return_value = None
        repo_mock.has_ai_message_after_db_id_in_session.return_value = False
        MockMR.return_value = repo_mock
        mgr = ConversationMemoryManager(db_mock, THREAD_ID, tenant_id=TENANT_ID, agent_id=AGENT_ID)

    return mgr, db_mock, repo_mock


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
    message_limit: int | None = None,
):
    """Wire mock return values and invoke load_messages_with_summary."""
    repo_mock.get_unsummarized_messages.return_value = list(unsummarized_msgs or [])
    repo_mock.get_last_ai_message_with_tool_calls.return_value = last_ai_tool
    repo_mock.get_messages_from_db_id.return_value = list(tail_msgs or [])

    with patch(_TSR_PATH) as MockTSR, patch(_SSR_PATH) as MockSSR:
        tsr_inst = AsyncMock()
        tsr_inst.get_recent_summaries.return_value = list(thread_summaries or [])
        MockTSR.return_value = tsr_inst

        ssr_inst = AsyncMock()
        ssr_inst.get_unsummarized_sessions.return_value = list(session_summaries or [])
        MockSSR.return_value = ssr_inst

        return await mgr.load_messages_with_summary(
            thread_summary_limit=thread_summary_limit,
            session_summary_limit=session_summary_limit,
            message_limit=message_limit,
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

    async def test_message_limit_zero_passes_zero_to_repo(self):
        """message_limit=0 means load zero unsummarized messages."""
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, message_limit=0)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            thread_id=THREAD_ID,
            agent_id=AGENT_ID,
            limit=0,
        )

    async def test_message_limit_none_passes_none_to_repo(self):
        """message_limit=None means no cap (load all unsummarized messages)."""
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, message_limit=None)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            thread_id=THREAD_ID,
            agent_id=AGENT_ID,
            limit=None,
        )

    async def test_message_limit_n_passes_n_to_repo(self):
        """message_limit=5 → repo receives limit=5."""
        mgr, _, repo_mock = _make_manager()
        await _load(mgr, repo_mock, message_limit=5)

        repo_mock.get_unsummarized_messages.assert_called_once_with(
            thread_id=THREAD_ID,
            agent_id=AGENT_ID,
            limit=5,
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


# ─────────────────────────────────────────────────────────────────────────────
# TestEnsureHitlContext
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEnsureHitlContext:
    """Verify _ensure_hitl_context injection logic in isolation."""

    async def test_no_last_ai_returns_messages_unchanged(self):
        """get_last_ai_message_with_tool_calls returns None → list untouched."""
        mgr, _, repo_mock = _make_manager()
        repo_mock.get_last_ai_message_with_tool_calls.return_value = None

        msgs = [_db_msg(1, "m1", "human", "Q"), _db_msg(2, "m2", "ai", "A")]
        result = await mgr._ensure_hitl_context(msgs)

        assert result is msgs
        repo_mock.get_messages_from_db_id.assert_not_called()

    async def test_anchor_already_in_loaded_messages_returns_unchanged(self):
        """Anchor present in loaded set → no injection, no extra DB call."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI with tool", tool_calls=[{"id": "tc1"}])
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor

        msgs = [anchor, _db_msg(20, "tool-1", "tool", "Result")]
        result = await mgr._ensure_hitl_context(msgs)

        assert result is msgs
        repo_mock.get_messages_from_db_id.assert_not_called()

    async def test_anchor_missing_injects_tail_in_correct_order(self):
        """Anchor cut off → get_messages_from_db_id fetches tail and merges in ASC order."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI with tool", tool_calls=[{"id": "tc1"}])
        tool_msg = _db_msg(20, "tool-1", "tool", "Result")
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_messages_from_db_id.return_value = [anchor, tool_msg]

        later_q = _db_msg(30, "h-1", "human", "Follow-up")
        result = await mgr._ensure_hitl_context([later_q])

        repo_mock.get_messages_from_db_id.assert_called_once_with(
            thread_id=THREAD_ID,
            agent_id=AGENT_ID,
            from_db_id=10,
        )
        assert len(result) == 3
        assert [m.id for m in result] == [10, 20, 30]

    async def test_tail_deduplicates_overlap_with_loaded(self):
        """Tail items already in loaded_msgs are not duplicated."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        tool_msg = _db_msg(20, "tool-1", "tool", "Result")
        later_q = _db_msg(30, "h-1", "human", "Q")

        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_messages_from_db_id.return_value = [anchor, tool_msg, later_q]

        # later_q is already in loaded; should appear only once
        result = await mgr._ensure_hitl_context([later_q])

        assert len(result) == 3
        assert [m.id for m in result] == [10, 20, 30]

    async def test_empty_tail_returns_original_list(self):
        """get_messages_from_db_id returns [] (unexpected) → original list returned."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI", tool_calls=[{"id": "tc1"}])
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_messages_from_db_id.return_value = []

        later_q = _db_msg(30, "h-1", "human", "Q")
        result = await mgr._ensure_hitl_context([later_q])

        assert result == [later_q]

    async def test_resolved_chain_skips_injection(self):
        """Completed AI→Tool→AI chains are not re-injected for HITL continuity."""
        mgr, _, repo_mock = _make_manager()

        anchor = _db_msg(10, "ai-1", "ai", "AI with tool", tool_calls=[{"id": "tc1"}])
        repo_mock.get_last_ai_message_with_tool_calls.return_value = anchor
        repo_mock.get_tool_message_by_call_id.return_value = _db_msg(20, "tool-1", "tool", "Result")
        repo_mock.has_ai_message_after_db_id_in_session.return_value = True

        later_q = _db_msg(40, "h-1", "human", "Follow-up")
        result = await mgr._ensure_hitl_context([later_q])

        assert result == [later_q]
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

        repo_mock.get_tool_message_by_call_id.assert_called_once_with(THREAD_ID, "tc1")
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

        async def get_tool_side_effect(thread_id, tool_call_id):
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
            }
        )

    async def test_empty_list_is_no_op(self):
        mgr, db_mock, repo_mock = _make_manager()
        await mgr.add_messages([], self._runnable_config())

        repo_mock.save_messages_batch.assert_not_called()
        db_mock.commit.assert_not_called()

    async def test_system_messages_are_filtered_out(self):
        """SystemMessages must never reach save_messages_batch."""
        mgr, _, repo_mock = _make_manager()
        repo_mock.get_messages_by_ids.return_value = []

        await mgr.add_messages(
            [SystemMessage(content="context"), HumanMessage(id="h1", content="Hello")],
            self._runnable_config(),
        )

        saved = repo_mock.save_messages_batch.call_args[0][0]
        assert len(saved) == 1
        assert saved[0].type == "human"

    async def test_duplicate_message_ids_are_skipped(self):
        """Messages whose IDs already exist in the DB are not re-saved."""
        mgr, _, repo_mock = _make_manager()

        existing = MagicMock()
        existing.message_id = "h1"
        repo_mock.get_messages_by_ids.return_value = [existing]

        await mgr.add_messages(
            [HumanMessage(id="h1", content="Already saved"), HumanMessage(id="h2", content="New")],
            self._runnable_config(),
        )

        saved = repo_mock.save_messages_batch.call_args[0][0]
        assert len(saved) == 1
        assert saved[0].message_id == "h2"

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

    async def test_message_count_incremented_by_saved_count(self):
        """Thread.message_count is increased by exactly the number of persisted messages."""
        mgr, db_mock, repo_mock = _make_manager()
        repo_mock.get_messages_by_ids.return_value = []
        db_mock.get.return_value.message_count = 3

        await mgr.add_messages(
            [HumanMessage(id="h1", content="A"), HumanMessage(id="h2", content="B")],
            self._runnable_config(),
        )

        assert db_mock.get.return_value.message_count == 5  # 3 + 2
