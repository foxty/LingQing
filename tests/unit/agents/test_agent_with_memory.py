"""Unit tests for AgentBase with run-scoped context (``agent_run_port``).

Tests load history, merge with the current turn, and persist via the chat adapter.
"""

import os
import tempfile

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.shared.db.models import AgentRun, AgentRunMessage, Base, ChatMessage, ChatThread
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.chat.conversation_memory_manager import ConversationMemoryManager

TEST_RUN_ID = "00000000-0000-4000-8000-000000000001"

# Integration suites may replace ``AgentBase._llm_call`` on the class; restore for unit isolation.
_ORIGINAL_LLM_CALL = AgentBase._llm_call


@pytest.fixture(autouse=True)
def _restore_agent_base_llm_call():
    from apps.tenant_app_service.agent_pool import get_agent_pool

    AgentBase._llm_call = _ORIGINAL_LLM_CALL
    get_agent_pool()._pool.clear()
    yield
    AgentBase._llm_call = _ORIGINAL_LLM_CALL
    get_agent_pool()._pool.clear()


async def _seed_agent_run(session: AsyncSession, thread: ChatThread, *, session_id: str = "test-session") -> str:
    session.add(
        AgentRun(
            id=TEST_RUN_ID,
            tenant_id=thread.tenant_id,
            thread_id=thread.id,
            agent_id=thread.agent_id,
            trigger_message_id="trigger-1",
            invoke_index=0,
            status="running",
            session_id=session_id,
        )
    )
    await session.flush()
    return TEST_RUN_ID


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables."""
    # Create a temporary directory for test data
    temp_dir = tempfile.mkdtemp()
    os.environ["DATA_ROOT_PATH"] = temp_dir
    yield
    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        session = async_session_factory()
        yield session
        await session.close()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def test_thread_with_history(async_session, runtime_context):
    """Create a thread with existing conversation history."""
    test_thread_id = "test-thread-integration"
    test_tenant_id = runtime_context.tenant.tenant_id
    test_agent_id = runtime_context.agent_id
    # Create thread
    thread = ChatThread(
        id=test_thread_id,
        tenant_id=test_tenant_id,
        user_id=runtime_context.user.user_id,
        agent_id=test_agent_id,
        title="Test Conversation",
        message_count=0,  # Start at 0, ConversationMemoryManager will update
    )
    async_session.add(thread)
    await _seed_agent_run(async_session, thread, session_id=runtime_context.session_id)
    await async_session.commit()

    manager = ConversationMemoryManager(
        async_session, thread.id, tenant_id=test_tenant_id, agent_id=test_agent_id, run_id=TEST_RUN_ID
    )

    lc_msg2 = AIMessage(id="msg-2", content="2+2 equals 4.")
    config = {"configurable": {"thread_id": test_thread_id, "runtime": runtime_context.model_dump()}}

    await manager.add_messages([lc_msg2], config)

    return thread


@pytest.mark.asyncio
class TestAgentWithMemory:
    """AgentBase graph tests with ``agent_run_port`` and seeded history."""

    async def test_agent_without_conversation_manager_works(
        self,
        async_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that agent raises error when runtime context is not provided in config.

        The new integrated message management requires runtime context in config.
        """
        # Patch AgentConfig and construct AgentBase with a manager
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)
        compiled_agent = await agent.compile()

        # Test execution without runtime context should raise ValueError
        with pytest.raises(ValueError, match="Runtime context is missing"):
            await compiled_agent.ainvoke(
                {
                    "messages": [HumanMessage(content="test")],
                    "loop_count": 0,
                    "tool_call_counts": {},
                },
                config={"configurable": {"thread_id": "test-thread"}},  # No runtime
            )

    async def test_graph_loads_and_merges_messages(
        self,
        async_session,
        test_thread_with_history,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
        monkeypatch,
    ):
        """Test that graph correctly loads and merges messages via load_history node.

        The load_history node loads historical messages from DB and merges with new user input.
        """
        # Patch AgentConfig and construct AgentBase with a manager
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)

        # Mock the _llm_call method to capture the state it receives BEFORE compiling
        received_state = None

        async def mock_llm_call(self, state, config):
            nonlocal received_state
            received_state = state
            from apps.tenant_app_service.agents.context import extract_runtime_context

            runtime = extract_runtime_context(config)
            current_messages = state.get("messages", [])
            return {
                "messages": current_messages
                + [
                    AIMessage(
                        id="merged-ai-msg",
                        content="Response",
                        additional_kwargs={"session_id": runtime.session_id},
                    )
                ],
                "loop_count": state.get("loop_count", 0) + 1,
            }

        monkeypatch.setattr(AgentBase, "_llm_call", mock_llm_call)

        compiled_agent = await agent.compile()

        # Update runtime context to match thread_id
        runtime_context.thread_id = test_thread_with_history.id

        # Execute with a new message
        new_message = HumanMessage(content="New question")
        config = {
            "configurable": {
                "thread_id": test_thread_with_history.id,
                "db_session": async_session,
                "runtime": runtime_context.model_dump(),
                "run_id": TEST_RUN_ID,
            }
        }
        from apps.tenant_app_service.chat.agent_run_port_adapter import chat_agent_run_port_for_run

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _test_app_db_session():
            yield async_session

        monkeypatch.setattr(
            "apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.app_db_session",
            _test_app_db_session,
        )
        config["configurable"]["agent_run_port"] = chat_agent_run_port_for_run(
            tenant_id=runtime_context.tenant.tenant_id,
            agent_id=runtime_context.agent_id,
            run_id=TEST_RUN_ID,
        )

        result = await compiled_agent.ainvoke(
            {"messages": [new_message], "loop_count": 0, "tool_call_counts": {}},
            config=config,
        )

        # Verify that _llm_call received merged state with historical messages
        assert received_state is not None
        messages = received_state["messages"]
        assert "New question" in messages[-1].content, (
            f"Third message should be 'New question', got: {messages[1].content}"
        )

        await async_session.commit()
        persisted = await async_session.execute(
            select(AgentRunMessage)
            .where(AgentRunMessage.thread_id == test_thread_with_history.id)
            .order_by(AgentRunMessage.created_at)
        )
        assert any("Response" in (m.content or "") for m in persisted.scalars().all())
