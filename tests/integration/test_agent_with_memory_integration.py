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

from apps.shared.db.models import Agent, ChatMessage, ChatThread, Tenant, User
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables."""
    temp_dir = tempfile.mkdtemp()
    os.environ["DATA_ROOT_PATH"] = temp_dir
    yield
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def test_thread_with_history(async_db_session, runtime_context):
    """Create a thread with existing conversation history."""
    test_thread_id = "test-thread-integration"
    test_tenant_id = runtime_context.tenant.tenant_id
    test_agent_id = runtime_context.agent_id

    tenant = await async_db_session.get(Tenant, test_tenant_id)
    if tenant is None:
        tenant = Tenant(
            id=test_tenant_id,
            name=runtime_context.tenant.tenant_name,
            slug=f"tenant-{test_tenant_id}",
            status="active",
        )
        async_db_session.add(tenant)
        await async_db_session.flush()

    user = await async_db_session.get(User, runtime_context.user.user_id)
    if user is None:
        user = User(
            id=runtime_context.user.user_id,
            username=runtime_context.user.username,
            email=f"{runtime_context.user.username}@example.com",
            hashed_password="hashed",
            role=runtime_context.user.role,
            tenant_id=test_tenant_id,
            status="active",
        )
        async_db_session.add(user)
        await async_db_session.flush()

    agent = await async_db_session.get(Agent, test_agent_id)
    if agent is None:
        agent = Agent(
            id=test_agent_id,
            tenant_id=test_tenant_id,
            owner_id=runtime_context.user.user_id,
            name=runtime_context.agent_name,
            description="test agent",
            system_prompt="test prompt",
            config={},
        )
        async_db_session.add(agent)
        await async_db_session.flush()

    thread = ChatThread(
        id=test_thread_id,
        tenant_id=test_tenant_id,
        user_id=runtime_context.user.user_id,
        agent_id=test_agent_id,
        title="Test Conversation",
        message_count=0,
    )
    async_db_session.add(thread)
    await async_db_session.commit()

    manager = ConversationMemoryManager(async_db_session, thread.id, tenant_id=test_tenant_id, agent_id=test_agent_id)

    lc_msg1 = HumanMessage(id="msg-1", content="Hello, what is 2+2?")
    lc_msg2 = AIMessage(id="msg-2", content="2+2 equals 4.")
    config = {"configurable": {"thread_id": test_thread_id, "runtime": runtime_context.model_dump()}}

    await manager.add_messages([lc_msg1, lc_msg2], config)

    return thread


@pytest.mark.asyncio
class TestAgentWithMemory:
    """Test suite for AgentBase with ConversationMemoryManager enabled."""

    async def test_agent_loads_conversation_history(
        self,
        async_db_session,
        runtime_context,
        test_thread_with_history,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that agent loads historical messages before execution."""
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="default-model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        agent = AgentBase(stub_config)
        await agent.compile()

        manager = ConversationMemoryManager(
            async_db_session,
            test_thread_with_history.id,
            tenant_id=runtime_context.tenant.tenant_id,
            agent_id=runtime_context.agent_id,
        )
        loaded_messages = await manager.load_messages_with_summary(message_limit=50)

        assert len(loaded_messages) == 2
        assert isinstance(loaded_messages[0], HumanMessage)
        assert "2+2" in loaded_messages[0].content
        assert isinstance(loaded_messages[1], AIMessage)
        assert "4" in loaded_messages[1].content

    async def test_agent_saves_new_messages_to_db(self, async_db_session, test_thread_with_history, runnable_config):
        """Test that agent saves new messages to database after execution."""
        initial_count = test_thread_with_history.message_count

        manager = ConversationMemoryManager(async_db_session, test_thread_with_history.id, tenant_id=1, agent_id=1)

        new_messages = [
            HumanMessage(content="Tell me a joke"),
            AIMessage(content="Why did the chicken cross the road? To get to the other side!"),
        ]

        await manager.add_messages(new_messages, runnable_config)

        await async_db_session.refresh(test_thread_with_history)

        assert test_thread_with_history.message_count == initial_count + 2

        result = await async_db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == test_thread_with_history.id)
            .order_by(ChatMessage.created_at)
        )
        all_messages = result.scalars().all()

        assert len(all_messages) == 4
        assert all_messages[2].type == "human"
        assert "joke" in all_messages[2].content
        assert all_messages[3].type == "ai"
        assert "chicken" in all_messages[3].content

    async def test_agent_without_conversation_manager_works(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that agent raises error when runtime context is not provided in config."""
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="test model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)
        compiled_agent = await agent.compile()

        with pytest.raises(ValueError, match="Runtime context is missing"):
            await compiled_agent.ainvoke(
                {
                    "messages": [HumanMessage(content="test")],
                    "loop_count": 0,
                    "tool_call_counts": {},
                },
                config={"configurable": {"thread_id": "test-thread"}},
            )

    async def test_graph_loads_and_merges_messages(
        self,
        async_db_session,
        test_thread_with_history,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that graph correctly loads and merges messages via load_history node."""
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="test model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)

        received_state = None

        async def mock_llm_call(state, config):
            nonlocal received_state
            received_state = state
            from apps.tenant_app_service.agents.context import extract_runtime_context

            runtime = extract_runtime_context(config)
            return {
                "messages": [AIMessage(content="Response", additional_kwargs={"session_id": runtime.session_id})],
                "loop_count": state.get("loop_count", 0) + 1,
            }

        agent._llm_call = mock_llm_call

        compiled_agent = await agent.compile()

        runtime_context.thread_id = test_thread_with_history.id

        new_message = HumanMessage(content="New question")
        config = {
            "configurable": {
                "thread_id": test_thread_with_history.id,
                "db_session": async_db_session,
                "runtime": runtime_context.model_dump(),
            }
        }

        await compiled_agent.ainvoke(
            {"messages": [new_message], "loop_count": 0, "tool_call_counts": {}},
            config=config,
        )

        assert received_state is not None
        messages = received_state["messages"]
        assert "New question" in messages[-1].content, (
            f"Third message should be 'New question', got: {messages[0].content}"
        )

    async def test_astream_saves_messages_to_db(
        self,
        async_db_session,
        test_thread_with_history,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that astream saves new messages to database via AgentWithMemory wrapper."""
        initial_count = test_thread_with_history.message_count

        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            model_key="test model",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)
        agent = AgentBase(stub_config)

        async def mock_llm_call(state, config):
            from apps.tenant_app_service.agents.context import extract_runtime_context

            runtime = extract_runtime_context(config)
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

        runtime_context.thread_id = test_thread_with_history.id

        config = {
            "configurable": {
                "thread_id": test_thread_with_history.id,
                "db_session": async_db_session,
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

        assert len(chunks) > 0

        await async_db_session.commit()
        await async_db_session.refresh(test_thread_with_history)

        assert test_thread_with_history.message_count == initial_count + 2

        result = await async_db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == test_thread_with_history.id)
            .order_by(ChatMessage.created_at)
        )
        all_messages = result.scalars().all()
        assert len(all_messages) == initial_count + 2
        assert "Stream test" in all_messages[-2].content
        assert "Streamed response" in all_messages[-1].content
