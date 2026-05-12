"""Integration tests for ConversationMemoryManager against real PostgreSQL.

Scenarios tested here cannot be validated with mocks because they depend on
PostgreSQL-specific behaviour:
  - JSON column storage and IS NOT NULL semantics for tool_calls
  - is_summarized=False filtering in SQL
  - ORDER BY (created_at, id) correctness across rows
  - Full save → load round-trip persistence
  - HITL injection end-to-end with real DB ids

Requires Docker daemon (container is started automatically by the pg_container
fixture in tests/integration/conftest.py).

Run with:
    uv run pytest tests/integration/test_conversation_memory_manager_integration.py -m integration
"""

from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatMessage, ChatThread, SessionSummary, ThreadSummary
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager

pytestmark = pytest.mark.integration

_BASE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def runnable_config() -> RunnableConfig:
    """Local runtime config aligned with sample_tenant_user_thread fixture.

    ConversationMemoryManager.add_messages stores agent_id from runtime context,
    while load_messages_with_summary filters by manager agent_id.  The global
    test fixture uses agent_id=456, but this integration suite uses
    sample_tenant_user_thread(agent_id=1, thread_id="integ-thread-001").
    Keep them consistent here to validate real round-trip behaviour.
    """
    return RunnableConfig(
        configurable={
            "thread_id": "integ-thread-001",
            "runtime": {
                "tenant": {"tenant_id": 1, "tenant_name": "integration-tenant", "config": {}},
                "user": {
                    "user_id": 123,
                    "username": "integ_user",
                    "role": "admin",
                    "tenant_id": 1,
                    "tenant_name": "integration-tenant",
                },
                "agent_id": 1,
                "agent_name": "test_agent",
                "thread_id": "integ-thread-001",
                "session_id": "session-integ-001",
            },
            "session_id": "session-integ-001",
        }
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _insert_msg(
    session: AsyncSession,
    *,
    thread_id: str,
    agent_id: int,
    msg_id: str,
    msg_type: str,
    content: str,
    is_summarized: bool = False,
    tool_calls: list | None = None,
    additional_kwargs: dict | None = None,
    session_id: str | None = None,
    t: int = 0,
) -> ChatMessage:
    ts = _BASE + timedelta(seconds=t)
    msg = ChatMessage(
        message_id=msg_id,
        thread_id=thread_id,
        agent_id=agent_id,
        type=msg_type,
        content=content,
        is_summarized=is_summarized,
        tool_calls=tool_calls,
        additional_kwargs=additional_kwargs or {},
        session_id=session_id,
        timestamp=ts,
        created_at=ts,
        message_metadata={},
    )
    session.add(msg)
    await session.flush()
    return msg


async def _insert_session_summary(
    session: AsyncSession,
    *,
    session_id: str,
    thread_id: str,
    tenant_id: int,
    summary_text: str,
    included_in_thread_summary: bool = False,
    created_at: datetime | None = None,
) -> SessionSummary:
    ss = SessionSummary(
        session_id=session_id,
        thread_id=thread_id,
        tenant_id=tenant_id,
        user_intent="intent",
        tools_used=[],
        key_results="results",
        summary_text=summary_text,
        message_range={"from_time": "2024-01-01", "to_time": "2024-01-01", "count": 1},
        included_in_thread_summary=included_in_thread_summary,
        created_at=created_at or _BASE,
    )
    session.add(ss)
    await session.flush()
    return ss


async def _insert_thread_summary(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: int,
    version: int = 1,
    summary_content: str,
) -> ThreadSummary:
    ts = ThreadSummary(
        thread_id=thread_id,
        tenant_id=tenant_id,
        version=version,
        summary_content=summary_content,
        session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
        message_range={"from_time": "2024-01-01", "to_time": "2024-01-01", "count": 5},
        session_count=1,
        token_count_before=100,
        token_count_after=50,
    )
    session.add(ts)
    await session.flush()
    return ts


def _manager(session: AsyncSession, thread: ChatThread) -> ConversationMemoryManager:
    return ConversationMemoryManager(session, thread.id, tenant_id=thread.tenant_id, agent_id=thread.agent_id)


# ─────────────────────────────────────────────────────────────────────────────
# TestSaveAndLoadRoundTrip
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSaveAndLoadRoundTrip:
    """Full persistence round-trips through real Postgres."""

    async def test_save_human_and_ai_then_load(self, pg_async_db_session, sample_tenant_user_thread, runnable_config):
        """Human + AI messages survive a save→load round-trip with correct types."""
        thread, *_ = sample_tenant_user_thread
        mgr = _manager(pg_async_db_session, thread)

        await mgr.add_messages(
            [HumanMessage(id="rt-h1", content="Hello"), AIMessage(id="rt-a1", content="Hi")],
            runnable_config,
        )

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 2
        assert isinstance(loaded[0], HumanMessage)
        assert loaded[0].content == "Hello"
        assert isinstance(loaded[1], AIMessage)
        assert loaded[1].content == "Hi"

    async def test_tool_message_round_trips_with_tool_call_id(
        self, pg_async_db_session, sample_tenant_user_thread, runnable_config
    ):
        """ToolMessage.tool_call_id is restored correctly after persist→load."""
        thread, *_ = sample_tenant_user_thread
        mgr = _manager(pg_async_db_session, thread)

        tc_id = "call_pg_test"
        await mgr.add_messages(
            [
                AIMessage(
                    id="rt-a2",
                    content="calling tool",
                    tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
                ),
                ToolMessage(id="rt-t1", content="Tool result", tool_call_id=tc_id),
            ],
            runnable_config,
        )

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].tool_calls[0]["id"] == tc_id
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[1].tool_call_id == tc_id

    async def test_system_messages_not_persisted(self, pg_async_db_session, sample_tenant_user_thread, runnable_config):
        """SystemMessages are filtered; only Human+AI reach the DB."""
        thread, *_ = sample_tenant_user_thread
        mgr = _manager(pg_async_db_session, thread)

        await mgr.add_messages(
            [
                SystemMessage(content="context prompt"),
                HumanMessage(id="rt-h3", content="Q"),
                AIMessage(id="rt-a3", content="A"),
            ],
            runnable_config,
        )

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 2
        assert all(not isinstance(m, SystemMessage) for m in loaded)

    async def test_messages_returned_in_chronological_order(self, pg_async_db_session, sample_tenant_user_thread):
        """Messages inserted at different timestamps come back in ASC created_at order."""
        thread, *_ = sample_tenant_user_thread
        mgr = _manager(pg_async_db_session, thread)

        for i, content in enumerate(["First", "Second", "Third", "Fourth"]):
            await _insert_msg(
                pg_async_db_session,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                msg_id=f"ord-{i}",
                msg_type="human",
                content=content,
                t=i * 10,
            )
        await pg_async_db_session.commit()

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert [m.content for m in loaded] == ["First", "Second", "Third", "Fourth"]


# ─────────────────────────────────────────────────────────────────────────────
# TestUnsummarizedFiltering
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUnsummarizedFiltering:
    """Validate is_summarized=False SQL filter on real Postgres JSON columns."""

    async def test_summarized_messages_excluded_from_load(self, pg_async_db_session, sample_tenant_user_thread):
        """Rows with is_summarized=True are excluded by the SQL query."""
        thread, *_ = sample_tenant_user_thread

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="f-0",
            msg_type="human",
            content="Old Q",
            is_summarized=True,
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="f-1",
            msg_type="ai",
            content="Old A",
            is_summarized=True,
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="f-2",
            msg_type="human",
            content="New Q",
            is_summarized=False,
            t=20,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 1
        assert loaded[0].content == "New Q"

    async def test_message_limit_applies_to_unsummarized_only(self, pg_async_db_session, sample_tenant_user_thread):
        """message_limit counts only unsummarized rows; summarized rows never fill the quota."""
        thread, *_ = sample_tenant_user_thread

        # 3 summarized (old)
        for i in range(3):
            await _insert_msg(
                pg_async_db_session,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                msg_id=f"ls-old-{i}",
                msg_type="human",
                content=f"Old {i}",
                is_summarized=True,
                t=i * 10,
            )
        # 5 unsummarized (new)
        for i in range(5):
            await _insert_msg(
                pg_async_db_session,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                msg_id=f"ls-new-{i}",
                msg_type="human",
                content=f"New {i}",
                is_summarized=False,
                t=(i + 3) * 10,
            )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=2
        )

        # Most recent 2 unsummarized = New 3, New 4
        assert len(loaded) == 2
        assert loaded[0].content == "New 3"
        assert loaded[1].content == "New 4"

    async def test_message_limit_zero_loads_zero_unsummarized_messages(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """message_limit=0 should load zero unsummarized messages (not all)."""
        thread, *_ = sample_tenant_user_thread

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="z-0",
            msg_type="human",
            content="Q0",
            is_summarized=False,
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="z-1",
            msg_type="ai",
            content="A1",
            is_summarized=False,
            t=10,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=0
        )

        assert loaded == []

    async def test_ai_message_with_null_tool_calls_excluded_from_hitl_search(
        self, pg_async_db_session, sample_tenant_user_thread, runnable_config
    ):
        """On Postgres, AIMessages with tool_calls=NULL are not returned by
        get_last_ai_message_with_tool_calls, so no spurious HITL injection occurs."""
        thread, *_ = sample_tenant_user_thread
        mgr = _manager(pg_async_db_session, thread)

        # AI without tool_calls → stored as NULL in Postgres
        await mgr.add_messages(
            [
                HumanMessage(id="pg-h1", content="Q1"),
                AIMessage(id="pg-a1", content="A1"),  # no tool_calls
                HumanMessage(id="pg-h2", content="Q2"),
            ],
            runnable_config,
        )

        # message_limit=1 should return only Q2, no HITL injection
        loaded = await mgr.load_messages_with_summary(thread_summary_limit=0, session_summary_limit=0, message_limit=1)

        assert len(loaded) == 1
        assert loaded[0].content == "Q2"


# ─────────────────────────────────────────────────────────────────────────────
# TestHITLEndToEnd
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHITLEndToEnd:
    """End-to-end HITL injection tests on real Postgres."""

    async def test_hitl_anchor_cut_off_by_limit_is_injected(self, pg_async_db_session, sample_tenant_user_thread):
        """AI+Tool outside the message_limit window are injected for HITL continuity."""
        thread, *_ = sample_tenant_user_thread
        tc_id = "call_pg_cutoff"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="hi-0",
            msg_type="ai",
            content="AI with tool",
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="hi-1",
            msg_type="tool",
            content="Tool result",
            additional_kwargs={"tool_call_id": tc_id},
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="hi-2",
            msg_type="human",
            content="After Q",
            t=20,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="hi-3",
            msg_type="human",
            content="Another Q",
            t=30,
        )
        await pg_async_db_session.commit()

        # message_limit=2 → unsummarized window = [After Q, Another Q]; AI+Tool cut off
        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=2
        )

        assert len(loaded) == 4
        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].tool_calls[0]["id"] == tc_id
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[1].tool_call_id == tc_id
        assert loaded[2].content == "After Q"
        assert loaded[3].content == "Another Q"

    async def test_summarized_ai_with_tool_calls_is_injected(self, pg_async_db_session, sample_tenant_user_thread):
        """Summarized AI+Tool are still injected when they are the most recent HITL anchor."""
        thread, *_ = sample_tenant_user_thread
        tc_id = "call_pg_summarized"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="sm-0",
            msg_type="ai",
            content="Summarized AI",
            is_summarized=True,
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="sm-1",
            msg_type="tool",
            content="Summarized result",
            is_summarized=True,
            additional_kwargs={"tool_call_id": tc_id},
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="sm-2",
            msg_type="human",
            content="New Q",
            is_summarized=False,
            t=20,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 3
        assert isinstance(loaded[0], AIMessage)
        assert len(loaded[0].tool_calls) > 0
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[2].content == "New Q"

    async def test_only_most_recent_ai_anchor_injected(self, pg_async_db_session, sample_tenant_user_thread):
        """When multiple AI messages have tool_calls, only the most recent is the anchor."""
        thread, *_ = sample_tenant_user_thread
        old_tc, new_tc = "call_pg_old", "call_pg_new"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mr-0",
            msg_type="ai",
            content="Old AI",
            tool_calls=[{"id": old_tc, "name": "t", "args": {}, "type": "tool_call"}],
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mr-1",
            msg_type="tool",
            content="Old result",
            additional_kwargs={"tool_call_id": old_tc},
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mr-2",
            msg_type="human",
            content="Middle Q",
            t=20,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mr-3",
            msg_type="ai",
            content="New AI",
            tool_calls=[{"id": new_tc, "name": "t", "args": {}, "type": "tool_call"}],
            t=30,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mr-4",
            msg_type="tool",
            content="New result",
            additional_kwargs={"tool_call_id": new_tc},
            t=40,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mr-5",
            msg_type="human",
            content="Latest Q",
            t=50,
        )
        await pg_async_db_session.commit()

        # limit=1 → window = [Latest Q]; injection anchor = New AI
        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=1
        )

        assert len(loaded) == 3
        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].content == "New AI"
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[1].content == "New result"
        assert loaded[2].content == "Latest Q"

    async def test_resolved_summarized_tool_chain_is_not_reinjected(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Summarized AI→Tool→AI chains stay compressed; only new unsummarized messages load."""
        thread, *_ = sample_tenant_user_thread
        tc_id = "call_pg_resolved"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="rs-0",
            msg_type="ai",
            content="AI with tool",
            is_summarized=True,
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            session_id="session-rs",
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="rs-1",
            msg_type="tool",
            content="Tool result",
            is_summarized=True,
            additional_kwargs={"tool_call_id": tc_id},
            session_id="session-rs",
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="rs-2",
            msg_type="ai",
            content="Final answer",
            is_summarized=True,
            session_id="session-rs",
            t=20,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="rs-3",
            msg_type="human",
            content="New Q",
            is_summarized=False,
            session_id="session-new",
            t=30,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 1
        assert loaded[0].content == "New Q"

    async def test_pending_tool_call_without_response_is_still_injected(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Summarized AI with pending tool_calls (no ToolMessage yet) must still be injected."""
        thread, *_ = sample_tenant_user_thread
        tc_id = "call_pg_pending"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="pd-0",
            msg_type="ai",
            content="AI awaiting tool execution",
            is_summarized=True,
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="pd-1",
            msg_type="human",
            content="New Q",
            is_summarized=False,
            t=10,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 2
        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].tool_calls[0]["id"] == tc_id
        assert loaded[1].content == "New Q"

    async def test_older_unresolved_chain_ignored_when_newer_anchor_resolved(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Only the most recent AI tool_call anchor matters; skip when that chain is resolved."""
        thread, *_ = sample_tenant_user_thread
        old_tc = "call_pg_old_pending"
        new_tc = "call_pg_new_resolved"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mx-0",
            msg_type="ai",
            content="Old pending AI",
            is_summarized=True,
            tool_calls=[{"id": old_tc, "name": "t", "args": {}, "type": "tool_call"}],
            session_id="session-old",
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mx-1",
            msg_type="human",
            content="Middle Q",
            is_summarized=True,
            session_id="session-old",
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mx-2",
            msg_type="ai",
            content="New AI with tool",
            is_summarized=True,
            tool_calls=[{"id": new_tc, "name": "t", "args": {}, "type": "tool_call"}],
            session_id="session-new",
            t=20,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mx-3",
            msg_type="tool",
            content="New tool result",
            is_summarized=True,
            additional_kwargs={"tool_call_id": new_tc},
            session_id="session-new",
            t=30,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mx-4",
            msg_type="ai",
            content="Final answer",
            is_summarized=True,
            session_id="session-new",
            t=40,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="mx-5",
            msg_type="human",
            content="Latest Q",
            is_summarized=False,
            session_id="session-latest",
            t=50,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=None
        )

        assert len(loaded) == 1
        assert loaded[0].content == "Latest Q"

    async def test_hitl_placeholder_tools_stay_unresolved_with_later_session_ai(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """HITL pending/skipped tool rows and cross-session AI must not mark the chain resolved."""
        thread, tenant_id, _ = sample_tenant_user_thread
        tc_id = "call_pg_hitl_open"

        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-0",
            msg_type="ai",
            content="AI awaiting approval",
            is_summarized=True,
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            session_id="session-hitl",
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-1",
            msg_type="tool",
            content="Tool 't' requires human approval.",
            is_summarized=True,
            additional_kwargs={
                "tool_call_id": tc_id,
                "hitl": {"type": "approval_request", "proposal_id": "hitl_open"},
            },
            session_id="session-hitl",
            t=10,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-2",
            msg_type="human",
            content="Unrelated follow-up",
            is_summarized=False,
            session_id="session-later",
            t=20,
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-3",
            msg_type="ai",
            content="Let me re-run the query now.",
            is_summarized=False,
            session_id="session-later",
            t=30,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, message_limit=1
        )

        assert len(loaded) == 4
        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].tool_calls[0]["id"] == tc_id
        assert [m.content for m in loaded if isinstance(m, HumanMessage)] == ["Unrelated follow-up"]


# ─────────────────────────────────────────────────────────────────────────────
# TestSummaryLoading
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSummaryLoading:
    """Validate summary loading and structural ordering on real Postgres."""

    async def test_only_unsummarized_session_summaries_shown(self, pg_async_db_session, sample_tenant_user_thread):
        """Sessions with included_in_thread_summary=True are excluded."""
        thread, tenant_id, _ = sample_tenant_user_thread

        await _insert_session_summary(
            pg_async_db_session,
            session_id="ss-old",
            thread_id=thread.id,
            tenant_id=tenant_id,
            summary_text="Old session",
            included_in_thread_summary=True,
        )
        await _insert_session_summary(
            pg_async_db_session,
            session_id="ss-new",
            thread_id=thread.id,
            tenant_id=tenant_id,
            summary_text="New session",
            included_in_thread_summary=False,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=5, message_limit=None
        )

        session_sys = [
            m
            for m in loaded
            if isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "session_summary"
        ]
        assert len(session_sys) == 1
        assert "New session" in session_sys[0].content
        assert "Old session" not in session_sys[0].content

    async def test_thread_summary_appears_before_all_other_messages(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """ThreadSummary SystemMessage is always output[0] regardless of other data."""
        thread, tenant_id, _ = sample_tenant_user_thread

        await _insert_thread_summary(
            pg_async_db_session, thread_id=thread.id, tenant_id=tenant_id, summary_content="Historical context"
        )
        await _insert_msg(
            pg_async_db_session,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ts-m1",
            msg_type="human",
            content="Recent Q",
            t=0,
        )
        await pg_async_db_session.commit()

        loaded = await _manager(pg_async_db_session, thread).load_messages_with_summary(
            thread_summary_limit=1, session_summary_limit=0, message_limit=None
        )

        assert isinstance(loaded[0], SystemMessage)
        assert loaded[0].additional_kwargs.get("summary_type") == "thread_summary"
        assert "Historical context" in loaded[0].content
        assert loaded[-1].content == "Recent Q"
