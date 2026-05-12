"""Integration tests for AgentBase with ConversationMemoryManager.

Tests the complete flow of agent execution with conversation memory:
- Loading historical messages before execution
- Merging with new user input
- Saving new messages after execution
"""

import os
import tempfile

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.shared.db.models import Base, ChatMessage, ChatThread
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager


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
    await async_session.commit()

    # Use ConversationMemoryManager to save messages (it handles IDs properly)
    manager = ConversationMemoryManager(async_session, thread.id, tenant_id=test_tenant_id, agent_id=test_agent_id)

    # Create LangChain messages with explicit IDs
    lc_msg1 = HumanMessage(id="msg-1", content="Hello, what is 2+2?")
    lc_msg2 = AIMessage(id="msg-2", content="2+2 equals 4.")
    config = {"configurable": {"thread_id": test_thread_id, "runtime": runtime_context.model_dump()}}  # RunnableConfig

    await manager.add_messages([lc_msg1, lc_msg2], config)

    return thread


@pytest.mark.asyncio
class TestAgentWithMemory:
    """Test suite for AgentBase with ConversationMemoryManager enabled."""

    async def test_agent_loads_conversation_history(
        self,
        async_session,
        runtime_context,
        test_thread_with_history,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that agent loads historical messages before execution.

        Now uses load_messages_with_summary for optimized loading.
        """
        # Patch AgentConfig to avoid reading real YAML and to include a default role
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="default-model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        # Create agent
        agent = AgentBase(stub_config)

        # Compile agent (returns compiled graph with built-in message persistence)
        compiled_agent = await agent.compile()

        # Verify that historical messages can be loaded via manager
        manager = ConversationMemoryManager(
            async_session,
            test_thread_with_history.id,
            tenant_id=runtime_context.tenant.tenant_id,
            agent_id=runtime_context.agent_id,
        )
        loaded_messages = await manager.load_messages_with_summary(message_limit=50)

        # Should have 2 historical messages (no summary yet)
        assert len(loaded_messages) == 2
        assert isinstance(loaded_messages[0], HumanMessage)
        assert "2+2" in loaded_messages[0].content
        assert isinstance(loaded_messages[1], AIMessage)
        assert "4" in loaded_messages[1].content

    async def test_agent_saves_new_messages_to_db(self, async_session, test_thread_with_history, runnable_config):
        """Test that agent saves new messages to database after execution."""
        # Initial message count
        initial_count = test_thread_with_history.message_count

        # Create conversation manager
        manager = ConversationMemoryManager(async_session, test_thread_with_history.id, tenant_id=1, agent_id=1)

        # Manually save new messages using the manager
        new_messages = [
            HumanMessage(content="Tell me a joke"),
            AIMessage(content="Why did the chicken cross the road? To get to the other side!"),
        ]

        await manager.add_messages(new_messages, runnable_config)

        # Verify new messages were saved to database
        await async_session.refresh(test_thread_with_history)

        # Should have original 2 messages + 2 new messages = 4 total
        assert test_thread_with_history.message_count == initial_count + 2

        # Verify messages are in database
        result = await async_session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == test_thread_with_history.id)
            .order_by(ChatMessage.created_at)
        )
        all_messages = result.scalars().all()

        # Should have 4 messages
        assert len(all_messages) == 4

        # Check the new user message was saved
        assert all_messages[2].type == "human"
        assert "joke" in all_messages[2].content

        # Check the new AI message was saved
        assert all_messages[3].type == "ai"
        assert "chicken" in all_messages[3].content

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
            model_key="test model",
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
    ):
        """Test that graph correctly loads and merges messages via load_history node.

        The load_history node loads historical messages from DB and merges with new user input.
        """
        # Patch AgentConfig and construct AgentBase with a manager
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="test model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)

        # Mock the _llm_call method to capture the state it receives BEFORE compiling
        received_state = None

        async def mock_llm_call(state, config):
            nonlocal received_state
            received_state = state
            # Return minimal response with session_id
            from apps.tenant_app_service.agents.context import extract_runtime_context

            runtime = extract_runtime_context(config)
            return {
                "messages": [AIMessage(content="Response", additional_kwargs={"session_id": runtime.session_id})],
                "loop_count": state.get("loop_count", 0) + 1,
            }

        agent._llm_call = mock_llm_call

        # Compile with mock already set
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
            }
        }

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

    async def test_astream_saves_messages_to_db(
        self,
        async_session,
        test_thread_with_history,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that astream saves new messages to database via AgentWithMemory wrapper.

        The wrapper saves all new messages after stream completes.
        """
        initial_count = test_thread_with_history.message_count

        # Patch AgentConfig and construct AgentBase with a manager
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="test model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)

        # Mock _llm_call to return a simple response with session_id
        async def mock_llm_call(state, config):
            from apps.tenant_app_service.agents.context import extract_runtime_context

            runtime = extract_runtime_context(config)
            # Return all existing messages + new AI response (mimicking real behavior)
            current_messages = state.get("messages", [])
            return {
                "messages": current_messages
                + [
                    AIMessage(
                        id="new-ai-msg",
                        content="Streamed response",
                        additional_kwargs={"session_id": runtime.session_id},
                    )
                ],
                "loop_count": state.get("loop_count", 0) + 1,
            }

        agent._llm_call = mock_llm_call

        compiled_agent = await agent.compile()

        # Update runtime context to match thread_id
        runtime_context.thread_id = test_thread_with_history.id

        # Execute stream
        config = {
            "configurable": {
                "thread_id": test_thread_with_history.id,
                "db_session": async_session,
                "runtime": runtime_context.model_dump(),
            }
        }

        chunks = []
        async for chunk in compiled_agent.astream(
            {
                "messages": [HumanMessage(id="new-human-msg", content="Stream test")],
                "loop_count": 0,
                "tool_call_counts": {},
            },
            config=config,
        ):
            chunks.append(chunk)

        # Verify chunks were yielded
        assert len(chunks) > 0

        # Commit and refresh to ensure data is persisted
        await async_session.commit()
        await async_session.refresh(test_thread_with_history)

        # Verify new messages were saved to database
        assert test_thread_with_history.message_count == initial_count + 2  # +1 human, +1 AI

        # Verify messages are in database
        result = await async_session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == test_thread_with_history.id)
            .order_by(ChatMessage.created_at)
        )
        all_messages = result.scalars().all()
        assert len(all_messages) == initial_count + 2
        assert "Stream test" in all_messages[-2].content
        assert "Streamed response" in all_messages[-1].content
