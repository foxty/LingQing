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

from apps.shared.db.models import (
    AgentRunMessage,
    ChatThread,
    SessionSummary,
    ThreadMainMessage,
    ThreadSummary,
)
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


async def _seed_run(
    session: AsyncSession,
    thread: ChatThread,
    *,
    trigger_message_id: str | None = None,
    session_id: str | None = None,
    agent_id: int | None = None,
    invoke_index: int = 0,
) -> tuple[str, str, str]:
    """Create agent_runs row; returns (run_id, trigger_message_id, session_id)."""
    from uuid import uuid4

    from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository

    trigger = trigger_message_id or str(uuid4())
    sess = session_id or str(uuid4())
    aid = agent_id if agent_id is not None else thread.agent_id
    run = await AgentRunRepository(session).create_run(
        tenant_id=thread.tenant_id,
        thread_id=thread.id,
        agent_id=aid,
        trigger_message_id=trigger,
        invoke_index=invoke_index,
        session_id=sess,
    )
    return run.id, trigger, sess


async def _insert_main_human(
    session: AsyncSession,
    *,
    thread_id: str,
    message_id: str,
    content: str,
    t: int = 0,
) -> ThreadMainMessage:
    ts = _BASE + timedelta(seconds=t)
    row = ThreadMainMessage(
        message_id=message_id,
        thread_id=thread_id,
        type="human",
        content=content,
        timestamp=ts,
        created_at=ts,
    )
    session.add(row)
    await session.flush()
    return row


async def _insert_main_ai(
    session: AsyncSession,
    *,
    thread_id: str,
    message_id: str,
    content: str,
    agent_id: int,
    trigger_message_id: str,
    agent_run_id: str,
    session_id: str,
    invoke_index: int = 0,
    t: int = 0,
) -> ThreadMainMessage:
    ts = _BASE + timedelta(seconds=t)
    row = ThreadMainMessage(
        message_id=message_id,
        thread_id=thread_id,
        type="ai",
        content=content,
        agent_id=agent_id,
        trigger_message_id=trigger_message_id,
        agent_run_id=agent_run_id,
        invoke_index=invoke_index,
        session_id=session_id,
        timestamp=ts,
        created_at=ts,
    )
    session.add(row)
    await session.flush()
    return row


async def _insert_run_msg(
    session: AsyncSession,
    *,
    run_id: str,
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
) -> AgentRunMessage:
    ts = _BASE + timedelta(seconds=t)
    msg = AgentRunMessage(
        message_id=msg_id,
        run_id=run_id,
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


async def _insert_msg(
    session: AsyncSession,
    *,
    thread_id: str,
    agent_id: int,
    msg_id: str,
    msg_type: str,
    content: str,
    run_id: str | None = None,
    is_summarized: bool = False,
    tool_calls: list | None = None,
    additional_kwargs: dict | None = None,
    session_id: str | None = None,
    t: int = 0,
):
    """Legacy helper: humans → main timeline; other types → agent_run_messages."""
    if msg_type == "human":
        return await _insert_main_human(
            session, thread_id=thread_id, message_id=msg_id, content=content, t=t
        )
    if not run_id:
        raise ValueError("run_id is required for non-human _insert_msg")
    return await _insert_run_msg(
        session,
        run_id=run_id,
        thread_id=thread_id,
        agent_id=agent_id,
        msg_id=msg_id,
        msg_type=msg_type,
        content=content,
        is_summarized=is_summarized,
        tool_calls=tool_calls,
        additional_kwargs=additional_kwargs,
        session_id=session_id,
        t=t,
    )


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


async def _manager(
    session: AsyncSession,
    thread: ChatThread,
    *,
    run_id: str | None = None,
    agent_id: int | None = None,
) -> ConversationMemoryManager:
    aid = agent_id if agent_id is not None else thread.agent_id
    if run_id is None:
        run_id, _, _ = await _seed_run(session, thread, agent_id=aid)
    return ConversationMemoryManager(
        session,
        thread.id,
        tenant_id=thread.tenant_id,
        agent_id=aid,
        run_id=run_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TestSaveAndLoadRoundTrip
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSaveAndLoadRoundTrip:
    """Full persistence round-trips through real Postgres."""

    async def test_save_human_and_ai_then_load(self, pg_async_db_session, sample_tenant_user_thread, runnable_config):
        """Human on main + AI on run survive save→load (main + run composition)."""
        thread, *_ = sample_tenant_user_thread
        run_id, trigger_id, session_id = await _seed_run(
            pg_async_db_session, thread, session_id="session-integ-001", trigger_message_id="rt-h1"
        )
        await _insert_main_human(
            pg_async_db_session, thread_id=thread.id, message_id=trigger_id, content="Hello"
        )
        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        config = RunnableConfig(
            configurable={
                **runnable_config["configurable"],
                "runtime": {
                    **runnable_config["configurable"]["runtime"],
                    "session_id": session_id,
                },
            }
        )

        await mgr.add_messages([AIMessage(id="rt-a1", content="Hi")], config)

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
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
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="session-integ-001")
        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        config = RunnableConfig(
            configurable={
                **runnable_config["configurable"],
                "runtime": {
                    **runnable_config["configurable"]["runtime"],
                    "session_id": session_id,
                },
            }
        )

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
            config,
        )

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].tool_calls[0]["id"] == tc_id
        assert isinstance(loaded[1], ToolMessage)
        assert loaded[1].tool_call_id == tc_id

    async def test_system_messages_not_persisted(self, pg_async_db_session, sample_tenant_user_thread, runnable_config):
        """SystemMessages are filtered; only run-scoped AI reaches the DB."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="session-integ-001")
        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        config = RunnableConfig(
            configurable={
                **runnable_config["configurable"],
                "runtime": {
                    **runnable_config["configurable"]["runtime"],
                    "session_id": session_id,
                },
            }
        )

        await mgr.add_messages(
            [
                SystemMessage(content="context prompt"),
                HumanMessage(id="rt-h3", content="Q"),
                AIMessage(id="rt-a3", content="A"),
            ],
            config,
        )

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert len(loaded) == 1
        assert isinstance(loaded[0], AIMessage)
        assert loaded[0].content == "A"

    async def test_messages_returned_in_chronological_order(self, pg_async_db_session, sample_tenant_user_thread):
        """Main timeline humans come back in ASC created_at order."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, _ = await _seed_run(pg_async_db_session, thread)
        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)

        for i, content in enumerate(["First", "Second", "Third", "Fourth"]):
            await _insert_main_human(
                pg_async_db_session,
                thread_id=thread.id,
                message_id=f"ord-{i}",
                content=content,
                t=i * 10,
            )
        await pg_async_db_session.commit()

        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert [m.content for m in loaded] == ["First", "Second", "Third", "Fourth"]


# ─────────────────────────────────────────────────────────────────────────────
# TestUnsummarizedFiltering
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUnsummarizedFiltering:
    """Validate is_summarized=False SQL filter on real Postgres JSON columns."""

    async def test_summarized_messages_excluded_from_load(self, pg_async_db_session, sample_tenant_user_thread):
        """Run rows with is_summarized=True are excluded; main humans still load."""
        thread, *_ = sample_tenant_user_thread
        old_run_id, _, old_sess = await _seed_run(pg_async_db_session, thread, session_id="sess-old")
        new_run_id, new_trigger, new_sess = await _seed_run(
            pg_async_db_session, thread, session_id="sess-new", trigger_message_id="f-2"
        )
        await _insert_main_human(pg_async_db_session, thread_id=thread.id, message_id="f-0", content="Old Q", t=0)
        await _insert_main_human(pg_async_db_session, thread_id=thread.id, message_id="f-2", content="New Q", t=20)
        await _insert_run_msg(
            pg_async_db_session,
            run_id=old_run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="f-1",
            msg_type="ai",
            content="Old A",
            is_summarized=True,
            session_id=old_sess,
            t=10,
        )
        await _insert_run_msg(
            pg_async_db_session,
            run_id=new_run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="f-3",
            msg_type="ai",
            content="New A",
            session_id=new_sess,
            t=30,
        )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=new_run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert [m.content for m in loaded if isinstance(m, HumanMessage)] == ["Old Q", "New Q"]
        assert [m.content for m in loaded if isinstance(m, AIMessage)] == ["New A"]

    async def test_turn_and_run_limits_apply_independently(self, pg_async_db_session, sample_tenant_user_thread):
        """main_timeline_turn_limit and run_message_limit cap each layer separately."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, sess = await _seed_run(pg_async_db_session, thread, session_id="sess-limit")
        for i in range(5):
            await _insert_main_human(
                pg_async_db_session,
                thread_id=thread.id,
                message_id=f"ls-new-{i}",
                content=f"New {i}",
                t=(i + 3) * 10,
            )
        for i in range(5):
            await _insert_run_msg(
                pg_async_db_session,
                run_id=run_id,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                msg_id=f"ls-run-{i}",
                msg_type="ai",
                content=f"Run {i}",
                is_summarized=i < 3,
                session_id=sess,
                t=(i + 3) * 10,
            )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=2, run_message_limit=2
        )

        # Main tail 2 + run unsummarized tail 2
        assert [m.content for m in loaded] == ["New 3", "New 4", "Run 3", "Run 4"]

    async def test_split_main_and_run_limits(self, pg_async_db_session, sample_tenant_user_thread):
        """main_timeline_turn_limit and run_message_limit are applied independently."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, sess = await _seed_run(pg_async_db_session, thread, session_id="sess-split")
        for i in range(4):
            await _insert_main_human(
                pg_async_db_session,
                thread_id=thread.id,
                message_id=f"sp-main-{i}",
                content=f"Main {i}",
                t=(i + 1) * 10,
            )
        for i in range(4):
            await _insert_run_msg(
                pg_async_db_session,
                run_id=run_id,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                msg_id=f"sp-run-{i}",
                msg_type="ai",
                content=f"Run {i}",
                session_id=sess,
                t=(i + 1) * 10,
            )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0,
            session_summary_limit=0,
            main_timeline_turn_limit=1,
            run_message_limit=None,
        )
        assert [m.content for m in loaded if m.content.startswith("Main")] == ["Main 3"]
        assert [m.content for m in loaded if m.content.startswith("Run")] == [
            "Run 0",
            "Run 1",
            "Run 2",
            "Run 3",
        ]

    async def test_main_timeline_turn_limit_keeps_human_and_promoted_ai(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """turn_limit=1 keeps one full exchange (human + AI), not a lone human."""
        thread, *_ = sample_tenant_user_thread
        run_id, trigger_id, sess = await _seed_run(pg_async_db_session, thread, session_id="sess-pair")
        await _insert_main_human(
            pg_async_db_session,
            thread_id=thread.id,
            message_id=trigger_id,
            content="Want a demo?",
            t=0,
        )
        await _insert_main_ai(
            pg_async_db_session,
            thread_id=thread.id,
            message_id="ai-offer",
            agent_id=thread.agent_id,
            trigger_message_id=trigger_id,
            agent_run_id=run_id,
            content="Say the word!",
            session_id=sess,
            t=10,
        )
        await _insert_main_human(
            pg_async_db_session,
            thread_id=thread.id,
            message_id="h-sure",
            content="sure",
            t=20,
        )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0,
            session_summary_limit=0,
            main_timeline_turn_limit=1,
            run_message_limit=0,
        )
        assert [m.content for m in loaded] == ["sure"]

        loaded_two = await mgr.load_messages_with_summary(
            thread_summary_limit=0,
            session_summary_limit=0,
            main_timeline_turn_limit=2,
            run_message_limit=0,
        )
        assert [m.content for m in loaded_two] == ["Want a demo?", "Say the word!", "sure"]

    async def test_zero_limits_load_no_main_or_run_messages(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """main_timeline_turn_limit=0, run_message_limit=0 should load zero main tail and zero run rows."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, sess = await _seed_run(pg_async_db_session, thread, session_id="sess-zero")

        await _insert_main_human(pg_async_db_session, thread_id=thread.id, message_id="z-0", content="Q0", t=0)
        await _insert_run_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="z-1",
            msg_type="ai",
            content="A1",
            session_id=sess,
            t=10,
        )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=0, run_message_limit=0
        )

        assert loaded == []

    async def test_ai_message_with_null_tool_calls_excluded_from_hitl_search(
        self, pg_async_db_session, sample_tenant_user_thread, runnable_config
    ):
        """On Postgres, AIMessages with tool_calls=NULL are not returned by
        get_last_ai_message_with_tool_calls, so no spurious HITL injection occurs."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="session-integ-001")
        await _insert_main_human(pg_async_db_session, thread_id=thread.id, message_id="pg-h1", content="Q1", t=0)
        await _insert_main_human(pg_async_db_session, thread_id=thread.id, message_id="pg-h2", content="Q2", t=20)
        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        config = RunnableConfig(
            configurable={
                **runnable_config["configurable"],
                "runtime": {
                    **runnable_config["configurable"]["runtime"],
                    "session_id": session_id,
                },
            }
        )

        await mgr.add_messages([AIMessage(id="pg-a1", content="A1")], config)

        # main_timeline_turn_limit=1, run_message_limit=1 caps main tail and run tail separately (no spurious HITL tool_calls)
        loaded = await mgr.load_messages_with_summary(thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=1, run_message_limit=1)

        assert len(loaded) == 2
        assert loaded[0].content == "Q2"
        assert loaded[1].content == "A1"
        assert not any(isinstance(m, AIMessage) and m.tool_calls for m in loaded)


# ─────────────────────────────────────────────────────────────────────────────
# TestHITLEndToEnd
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHITLEndToEnd:
    """End-to-end HITL injection tests on real Postgres."""

    async def test_hitl_anchor_cut_off_by_limit_is_injected(self, pg_async_db_session, sample_tenant_user_thread):
        """AI+Tool outside the run window are injected for HITL continuity."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="hitl-sess")
        tc_id = "call_pg_cutoff"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="hi-0",
            msg_type="ai",
            content="AI with tool",
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            session_id=session_id,
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="hi-1",
            msg_type="tool",
            content="Tool result",
            additional_kwargs={"tool_call_id": tc_id},
            session_id=session_id,
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

        # main_timeline_turn_limit=2, run_message_limit=2 → unsummarized window = [After Q, Another Q]; AI+Tool cut off
        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=2, run_message_limit=2
        )

        assert len(loaded) == 4
        assert loaded[0].content == "After Q"
        assert loaded[1].content == "Another Q"
        assert isinstance(loaded[2], AIMessage)
        assert loaded[2].tool_calls[0]["id"] == tc_id
        assert isinstance(loaded[3], ToolMessage)
        assert loaded[3].tool_call_id == tc_id

    async def test_summarized_ai_with_tool_calls_is_injected(self, pg_async_db_session, sample_tenant_user_thread):
        """Summarized AI+Tool are still injected when they are the most recent HITL anchor."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="hitl-sess")
        tc_id = "call_pg_summarized"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
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
            run_id=run_id,
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
            t=20,
        )
        await pg_async_db_session.commit()

        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert len(loaded) == 3
        assert loaded[0].content == "New Q"
        assert isinstance(loaded[1], AIMessage)
        assert len(loaded[1].tool_calls) > 0
        assert isinstance(loaded[2], ToolMessage)

    async def test_only_most_recent_ai_anchor_injected(self, pg_async_db_session, sample_tenant_user_thread):
        """When multiple AI messages have tool_calls, only the most recent is the anchor."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="hitl-sess")
        old_tc, new_tc = "call_pg_old", "call_pg_new"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
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
            run_id=run_id,
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
            run_id=run_id,
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
            run_id=run_id,
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
        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=1, run_message_limit=1
        )

        assert len(loaded) == 3
        assert loaded[0].content == "Latest Q"
        assert isinstance(loaded[1], AIMessage)
        assert loaded[1].content == "New AI"
        assert isinstance(loaded[2], ToolMessage)
        assert loaded[2].content == "New result"

    async def test_resolved_summarized_tool_chain_is_not_reinjected(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Summarized AI→Tool→AI chains stay compressed; only new unsummarized messages load."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="hitl-sess")
        tc_id = "call_pg_resolved"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
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
            run_id=run_id,
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
            run_id=run_id,
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

        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert len(loaded) == 1
        assert loaded[0].content == "New Q"

    async def test_pending_tool_call_without_response_is_still_injected(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Summarized AI with pending tool_calls (no ToolMessage yet) must still be injected."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="hitl-sess")
        tc_id = "call_pg_pending"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
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

        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert len(loaded) == 2
        assert loaded[0].content == "New Q"
        assert isinstance(loaded[1], AIMessage)
        assert loaded[1].tool_calls[0]["id"] == tc_id

    async def test_older_unresolved_chain_ignored_when_newer_anchor_resolved(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Only the most recent AI tool_call anchor matters; skip when that chain is resolved."""
        thread, *_ = sample_tenant_user_thread
        run_id, _, session_id = await _seed_run(pg_async_db_session, thread, session_id="hitl-sess")
        old_tc = "call_pg_old_pending"
        new_tc = "call_pg_new_resolved"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
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
            run_id=run_id,
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
            run_id=run_id,
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
            run_id=run_id,
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

        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert len(loaded) == 1
        assert loaded[0].content == "Latest Q"

    async def test_hitl_placeholder_tools_stay_unresolved_with_later_session_ai(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """HITL pending/skipped tool rows and cross-session AI must not mark the chain resolved."""
        thread, tenant_id, _ = sample_tenant_user_thread
        run_id, _, _ = await _seed_run(pg_async_db_session, thread, session_id="session-hitl")
        tc_id = "call_pg_hitl_open"

        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-0",
            msg_type="ai",
            content="AI awaiting approval",
            is_summarized=False,
            tool_calls=[{"id": tc_id, "name": "t", "args": {}, "type": "tool_call"}],
            session_id="session-hitl",
            t=0,
        )
        await _insert_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-1",
            msg_type="tool",
            content="Tool 't' requires human approval.",
            is_summarized=False,
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
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="ho-3",
            msg_type="ai",
            content="Let me re-run the query now.",
            is_summarized=True,
            session_id="session-later",
            t=30,
        )
        await pg_async_db_session.commit()

        loaded = await (await _manager(pg_async_db_session, thread, run_id=run_id)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert [m.content for m in loaded if isinstance(m, HumanMessage)] == ["Unrelated follow-up"]
        ai_with_tools = [m for m in loaded if isinstance(m, AIMessage) and m.tool_calls]
        assert len(ai_with_tools) == 1
        assert ai_with_tools[0].tool_calls[0]["id"] == tc_id
        assert any(isinstance(m, ToolMessage) for m in loaded)
        assert not any(
            isinstance(m, AIMessage) and m.content == "Let me re-run the query now." for m in loaded
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestMainTimelineRunContextDedup
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMainTimelineRunContextDedup:
    """Main timeline + run composition and summary dedup on real Postgres."""

    async def test_session_summary_omits_covered_main_ai_keeps_human(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        thread, tenant_id, _ = sample_tenant_user_thread
        trigger = "dedup-trigger-1"
        run_id, _, session_id = await _seed_run(
            pg_async_db_session,
            thread,
            trigger_message_id=trigger,
            session_id="dedup-sess-1",
        )
        await _insert_main_human(
            pg_async_db_session, thread_id=thread.id, message_id=trigger, content="User question", t=0
        )
        await _insert_main_ai(
            pg_async_db_session,
            thread_id=thread.id,
            message_id="dedup-ai-main",
            content="Promoted answer",
            agent_id=thread.agent_id,
            trigger_message_id=trigger,
            agent_run_id=run_id,
            session_id=session_id,
            t=10,
        )
        await _insert_session_summary(
            pg_async_db_session,
            session_id=session_id,
            thread_id=thread.id,
            tenant_id=tenant_id,
            summary_text="Session recap text",
        )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=1, main_timeline_turn_limit=None, run_message_limit=None
        )

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert [m.content for m in conv if isinstance(m, HumanMessage)] == ["User question"]
        assert not any(isinstance(m, AIMessage) and m.content == "Promoted answer" for m in conv)
        assert any(
            isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "session_summary"
            for m in loaded
        )

    async def test_promoted_main_not_duplicated_from_run_messages(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        thread, *_ = sample_tenant_user_thread
        trigger = "dedup-trigger-2"
        run_id, _, session_id = await _seed_run(
            pg_async_db_session,
            thread,
            trigger_message_id=trigger,
            session_id="dedup-sess-2",
        )
        await _insert_main_human(
            pg_async_db_session, thread_id=thread.id, message_id=trigger, content="Q", t=0
        )
        await _insert_main_ai(
            pg_async_db_session,
            thread_id=thread.id,
            message_id="dedup-final",
            content="Final",
            agent_id=thread.agent_id,
            trigger_message_id=trigger,
            agent_run_id=run_id,
            session_id=session_id,
            t=10,
        )
        await _insert_run_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="dedup-final",
            msg_type="ai",
            content="Final",
            session_id=session_id,
            t=10,
        )
        await _insert_run_msg(
            pg_async_db_session,
            run_id=run_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            msg_id="dedup-tool",
            msg_type="tool",
            content="tool output",
            additional_kwargs={"tool_call_id": "tc-dedup"},
            session_id=session_id,
            t=20,
        )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        finals = [m for m in loaded if getattr(m, "content", None) == "Final"]
        assert len(finals) == 1
        assert isinstance(finals[0], AIMessage)
        assert any(isinstance(m, ToolMessage) for m in loaded)

    async def test_multi_agent_same_trigger_summarized_peer_ai_omitted(
        self, pg_async_db_session, sample_tenant_user_thread
    ):
        """Agent B loader keeps shared human; agent A promoted AI omitted when A session summarized."""
        thread, tenant_id, _ = sample_tenant_user_thread
        trigger = "multi-trigger"
        peer_agent_id = thread.agent_id + 1000
        run_a, _, sess_a = await _seed_run(
            pg_async_db_session,
            thread,
            trigger_message_id=trigger,
            session_id="multi-sess-a",
            agent_id=peer_agent_id,
            invoke_index=0,
        )
        run_b, _, sess_b = await _seed_run(
            pg_async_db_session,
            thread,
            trigger_message_id=trigger,
            session_id="multi-sess-b",
            agent_id=thread.agent_id,
            invoke_index=1,
        )
        await _insert_main_human(
            pg_async_db_session, thread_id=thread.id, message_id=trigger, content="Shared ask", t=0
        )
        await _insert_main_ai(
            pg_async_db_session,
            thread_id=thread.id,
            message_id="multi-ai-a",
            content="Agent A reply",
            agent_id=peer_agent_id,
            trigger_message_id=trigger,
            agent_run_id=run_a,
            session_id=sess_a,
            invoke_index=0,
            t=10,
        )
        await _insert_main_ai(
            pg_async_db_session,
            thread_id=thread.id,
            message_id="multi-ai-b",
            content="Agent B reply",
            agent_id=thread.agent_id,
            trigger_message_id=trigger,
            agent_run_id=run_b,
            session_id=sess_b,
            invoke_index=1,
            t=11,
        )
        await _insert_session_summary(
            pg_async_db_session,
            session_id=sess_a,
            thread_id=thread.id,
            tenant_id=tenant_id,
            summary_text="Agent A session summary",
        )
        await pg_async_db_session.commit()

        mgr = await _manager(pg_async_db_session, thread, run_id=run_b, agent_id=thread.agent_id)
        loaded = await mgr.load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=1, main_timeline_turn_limit=None, run_message_limit=None
        )

        conv = [m for m in loaded if not isinstance(m, SystemMessage)]
        assert any(isinstance(m, HumanMessage) and m.content == "Shared ask" for m in conv)
        assert any(isinstance(m, AIMessage) and m.content == "Agent B reply" for m in conv)
        assert not any(isinstance(m, AIMessage) and m.content == "Agent A reply" for m in conv)


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

        loaded = await (await _manager(pg_async_db_session, thread)).load_messages_with_summary(
            thread_summary_limit=0, session_summary_limit=5, main_timeline_turn_limit=None, run_message_limit=None
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
        await _insert_main_human(
            pg_async_db_session, thread_id=thread.id, message_id="ts-m1", content="Recent Q", t=0
        )
        await pg_async_db_session.commit()

        loaded = await (await _manager(pg_async_db_session, thread)).load_messages_with_summary(
            thread_summary_limit=1, session_summary_limit=0, main_timeline_turn_limit=None, run_message_limit=None
        )

        assert isinstance(loaded[0], SystemMessage)
        assert loaded[0].additional_kwargs.get("summary_type") == "thread_summary"
        assert "Historical context" in loaded[0].content
        assert loaded[-1].content == "Recent Q"
