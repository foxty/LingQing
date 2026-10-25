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

from apps.shared.db.models import Agent, AgentRun, AgentRunMessage, ChatMessage, ChatThread, Tenant, User
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager

pytestmark = pytest.mark.integration

TEST_RUN_ID = "00000000-0000-4000-8000-000000000002"


async def _seed_agent_run(session, thread: ChatThread, *, session_id: str = "test-session") -> str:
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

    from tests.integration.helpers.runtime_seed import ensure_runtime_base_records

    await ensure_runtime_base_records(
        async_db_session,
        runtime_context,
        agent_system_prompt="test prompt",
        thread_id=test_thread_id,
        thread_title="Test Conversation",
    )

    thread = await async_db_session.get(ChatThread, test_thread_id)
    assert thread is not None

    await _seed_agent_run(async_db_session, thread, session_id=runtime_context.session_id)
    manager = ConversationMemoryManager(
        async_db_session, thread.id, tenant_id=test_tenant_id, agent_id=test_agent_id, run_id=TEST_RUN_ID
    )

    lc_msg2 = AIMessage(id="msg-2", content="2+2 equals 4.")
    config = {"configurable": {"thread_id": test_thread_id, "runtime": runtime_context.model_dump()}}

    await manager.add_messages([lc_msg2], config)

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
            run_id=TEST_RUN_ID,
        )
        loaded_messages = await manager.load_messages_with_summary(
            main_timeline_turn_limit=50,
            run_message_limit=50,
        )

        assert len(loaded_messages) == 1
        assert isinstance(loaded_messages[0], AIMessage)
        assert "4" in loaded_messages[0].content

    async def test_agent_saves_new_messages_to_db(self, async_db_session, test_thread_with_history, runnable_config):
        """Test that agent saves new messages to database after execution."""
        manager = ConversationMemoryManager(
            async_db_session, test_thread_with_history.id, tenant_id=1, agent_id=1, run_id=TEST_RUN_ID
        )

        new_messages = [
            AIMessage(content="Why did the chicken cross the road? To get to the other side!"),
        ]

        await manager.add_messages(new_messages, runnable_config)

        result = await async_db_session.execute(
            select(AgentRunMessage)
            .where(AgentRunMessage.thread_id == test_thread_with_history.id)
            .order_by(AgentRunMessage.created_at)
        )
        run_msgs = result.scalars().all()
        assert len(run_msgs) == 2
        assert "chicken" in run_msgs[-1].content

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
                "run_id": TEST_RUN_ID,
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
                "run_id": TEST_RUN_ID,
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

        result = await async_db_session.execute(
            select(AgentRunMessage)
            .where(AgentRunMessage.thread_id == test_thread_with_history.id)
            .order_by(AgentRunMessage.created_at)
        )
        all_messages = result.scalars().all()
        assert any("Streamed response" in (m.content or "") for m in all_messages)
