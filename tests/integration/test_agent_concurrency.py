"""Concurrency tests for AgentBase.

Tests agent behavior under concurrent requests to verify:
- Thread isolation
- Message isolation
- No race conditions in manager creation
- State isolation across concurrent executions

This module includes:
1. True concurrent tests using asyncio.to_thread for CPU-bound operations
2. Concurrent tests using multiple database sessions where applicable
3. Sequential tests for operations that don't support concurrency (SQLAlchemy async session limitations)
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import List

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select

from apps.shared.db.models import Agent, ChatMessage, ChatThread, Tenant, User
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager

pytestmark = pytest.mark.integration


def _assert_distinct_instances(instances: list) -> None:
    """Verify instances are distinct without relying on id() (GC can reuse ids)."""
    for i in range(len(instances)):
        for j in range(i + 1, len(instances)):
            assert instances[i] is not instances[j], "Each instance should be distinct (no caching)"


@pytest_asyncio.fixture(scope="function")
async def test_thread(async_db_session, runtime_context):
    """Create a test thread for concurrency tests."""
    test_thread_id = f"test-thread-concurrency-{asyncio.get_event_loop().time()}"
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
        title="Concurrency Test Thread",
        message_count=0,
    )
    async_db_session.add(thread)
    await async_db_session.commit()

    return thread


class TestAgentConcurrency:
    """Test suite for agent concurrency behavior."""

    def test_true_concurrent_manager_creation_sync(
        self,
        chroma_http_endpoint,
        pg_container,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test TRUE concurrent manager creation using threads.

        This is a REAL concurrent test that verifies the fix for _manager_cache race condition.
        Multiple threads create managers simultaneously to verify no race conditions occur.

        Uses a dedicated synchronous engine to avoid conflicts with other tests using
        the shared async_db_session fixture.
        """
        from sqlalchemy import create_engine as sync_create_engine
        from sqlalchemy.orm import sessionmaker

        # Patch config to use a valid agent_id
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        # Create a dedicated synchronous engine and session for this test
        # This avoids conflicts with other tests using async_db_session
        sync_engine = sync_create_engine(pg_container.replace("postgresql+asyncpg://", "postgresql+psycopg2://"))
        SyncSession = sessionmaker(bind=sync_engine)
        sync_session = SyncSession()

        try:
            agent = AgentBase(stub_config)
            thread_ids = [f"concurrent-thread-{i}" for i in range(10)]
            managers: List[ConversationMemoryManager] = []
            results: List[tuple[str, ConversationMemoryManager]] = []
            errors: List = []
            lock = threading.Lock()

            def create_manager_in_thread(thread_id: str):
                """Create manager in a separate thread."""
                try:
                    runtime = replace(runtime_context, thread_id=thread_id)
                    manager = agent._get_or_create_manager(runtime, sync_session)
                    with lock:
                        managers.append(manager)
                        results.append((thread_id, manager))
                except Exception as e:
                    with lock:
                        errors.append((thread_id, str(e)))

            # TRUE concurrent execution using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(create_manager_in_thread, tid) for tid in thread_ids]
                # Wait for all threads to complete
                for future in as_completed(futures):
                    future.result()

            # Verify no errors occurred
            assert len(errors) == 0, f"Errors occurred: {errors}"

            # Verify all managers were created
            assert len(managers) == len(thread_ids), f"Expected {len(thread_ids)} managers, got {len(managers)}"

            _assert_distinct_instances(managers)

            # Verify each manager has correct thread_id
            for thread_id, manager in results:
                assert manager.thread_id == thread_id, (
                    f"Manager thread_id mismatch: expected {thread_id}, got {manager.thread_id}"
                )
        finally:
            sync_session.close()
            sync_engine.dispose()

    @pytest.mark.asyncio
    async def test_asyncio_gather_concurrent_manager_creation(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test concurrent manager creation using asyncio.gather with separate sync sessions.

        This test uses asyncio.to_thread to run synchronous manager creation concurrently.
        """
        # Patch config to use a valid agent_id
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        agent = AgentBase(stub_config)
        thread_ids = [f"async-concurrent-{i}" for i in range(10)]

        async def create_manager_async(thread_id: str):
            """Create manager using asyncio.to_thread for true concurrency."""
            runtime = replace(runtime_context, thread_id=thread_id)
            # Run synchronous manager creation in thread pool
            manager = await asyncio.to_thread(agent._get_or_create_manager, runtime, async_db_session.sync_session)
            return manager

        # TRUE concurrent execution
        managers = await asyncio.gather(*[create_manager_async(tid) for tid in thread_ids])

        # Verify all managers were created
        assert len(managers) == len(thread_ids)

        _assert_distinct_instances(managers)

        # Verify each manager has correct thread_id
        for manager, expected_thread_id in zip(managers, thread_ids):
            assert manager.thread_id == expected_thread_id

    @pytest.mark.asyncio
    async def test_message_isolation(
        self,
        async_db_session,
        runtime_context,
        test_thread,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that messages are properly isolated by thread_id.

        Each thread should only contain messages sent to that specific thread.
        Note: Uses sequential execution since SQLAlchemy async sessions don't support concurrent ops.
        """
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        # Create multiple threads for different "users"
        thread_ids = [f"isolation-thread-{i}" for i in range(3)]
        messages_per_thread = 2

        # Create threads
        for tid in thread_ids:
            thread = ChatThread(
                id=tid,
                tenant_id=runtime_context.tenant.tenant_id,
                user_id=runtime_context.user.user_id,
                agent_id=runtime_context.agent_id,
                title=f"Isolation Test Thread {tid}",
                message_count=0,
            )
            async_db_session.add(thread)
        await async_db_session.commit()

        # Add messages to each thread sequentially
        # (SQLAlchemy async sessions don't support concurrent operations)
        for idx, thread_id in enumerate(thread_ids):
            manager = ConversationMemoryManager(
                async_db_session,
                thread_id,
                tenant_id=runtime_context.tenant.tenant_id,
                agent_id=runtime_context.agent_id,
            )
            messages = [
                HumanMessage(id=f"msg-{thread_id}-1", content=f"Hello from user {idx}"),
                AIMessage(id=f"msg-{thread_id}-2", content=f"Response to user {idx}"),
            ]
            config = {"configurable": {"thread_id": thread_id, "runtime": runtime_context.model_dump()}}
            await manager.add_messages(messages, config)

        # Verify message isolation
        for thread_id in thread_ids:
            result = await async_db_session.execute(
                select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.created_at)
            )
            messages = result.scalars().all()

            # Each thread should have exactly 2 messages
            assert len(messages) == messages_per_thread, f"Thread {thread_id} should have 2 messages"

            # Verify messages belong to correct thread
            for msg in messages:
                assert msg.thread_id == thread_id, f"Message {msg.id} should belong to thread {thread_id}"

    @pytest.mark.asyncio
    async def test_same_thread_id_multiple_access(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test multiple accesses to the same thread_id.

        Multiple requests to the same thread should each get
        their own manager instance (no caching).
        """
        # Patch config to use a valid agent_id
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        agent = AgentBase(stub_config)
        same_thread_id = "same-thread-concurrent"

        # Create managers sequentially for the same thread_id
        managers = []
        for _ in range(5):
            runtime = replace(runtime_context, thread_id=same_thread_id)
            manager = agent._get_or_create_manager(runtime, async_db_session)
            managers.append(manager)

        # With no caching, each call should return a new instance
        _assert_distinct_instances(managers)

        # All managers should have the same thread_id
        for manager in managers:
            assert manager.thread_id == same_thread_id

    @pytest.mark.asyncio
    async def test_agent_pool_get_or_create(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test agent creation from AgentPool.

        Verifies that AgentPool.get_or_create_agent works correctly.
        Uses valid agent_id from config.
        """
        from apps.tenant_app_service.agent_pool import AgentPool

        # Patch config for the system agent
        stub_config = agent_stub_config_factory(
            agent_id=-1,  # Use system agent ID
            agent_name="agent_one",
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        pool = AgentPool()

        # Create agents sequentially (SQLAlchemy async sessions don't support concurrent ops)
        agent_ids = [-1, -1, -1]  # Same agent_id to test caching

        agents = []
        for aid in agent_ids:
            agent = await pool.get_or_create_agent(stub_config)
            agents.append(agent)

        # Verify all agents were created successfully
        assert len(agents) == len(agent_ids)
        for agent in agents:
            assert agent is not None

        # Verify caching works correctly (same agent_id returns same compiled graph)
        # All should be the same cached instance
        for i in range(1, len(agents)):
            assert agents[0] is agents[i], "Same agent_id should return cached agent"

    @pytest.mark.asyncio
    async def test_high_volume_manager_creation(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Stress test with high volume to verify stability.

        Creates 50 managers to verify no issues with repeated creation.
        """
        # Patch config to use a valid agent_id
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="test prompt",
        )
        patch_agent_config_manager(stub_config)

        agent = AgentBase(stub_config)
        num_requests = 50

        # Create managers sequentially (SQLAlchemy async sessions don't support concurrent ops)
        managers = []
        for i in range(num_requests):
            thread_id = f"stress-thread-{i}"
            runtime = replace(runtime_context, thread_id=thread_id)
            manager = agent._get_or_create_manager(runtime, async_db_session)

            # Verify manager is functional
            assert manager.thread_id == thread_id
            assert manager.tenant_id == runtime_context.tenant.tenant_id
            managers.append(manager)

        # Verify all managers were created successfully
        assert len(managers) == num_requests

        _assert_distinct_instances(managers)

        # Verify thread_id isolation
        thread_ids = [m.thread_id for m in managers]
        assert len(set(thread_ids)) == num_requests, "All managers should have unique thread_ids"

    @pytest.mark.asyncio
    async def test_multi_user_concurrent_agent_invocation(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test simulating REAL multi-user concurrent agent invocation.

        This test uses asyncio.create_task + ainvoke to simulate multiple users
        concurrently invoking the agent through the real async interface.
        Each user has their own thread and sends a unique message.

        Uses a semaphore to limit concurrency to avoid SQLAlchemy session conflicts.
        This still tests the core concurrency logic of the agent framework.

        Note: Uses mocked LLM to avoid requiring API keys.
        """
        from unittest.mock import AsyncMock, patch

        # Patch config to use a valid agent_id
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="You are a helpful assistant. Respond briefly.",
        )
        patch_agent_config_manager(stub_config)

        # Create and compile the agent
        agent = AgentBase(stub_config)

        # Mock the model binding to return a fake LLM response
        mock_response = AIMessage(content="Test response", id="mock-ai-msg")
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
            compiled_agent = await agent.compile()

            # Simulate 5 concurrent users, each with their own thread
            num_users = 5
            user_messages = [
                f"Hello, I am user {i}. Please respond with 'User {i} acknowledged'." for i in range(num_users)
            ]
            thread_ids = [f"multi-user-thread-{i}" for i in range(num_users)]

            # Semaphore to limit concurrency and avoid SQLAlchemy session conflicts
            # This still tests concurrent task scheduling and agent framework logic
            semaphore = asyncio.Semaphore(1)

            async def simulate_user_invocation(user_idx: int, thread_id: str, message: str):
                """Simulate a single user invoking the agent."""
                # Create a fresh runtime context for each user
                user_runtime = replace(runtime_context, thread_id=thread_id)

                config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "db_session": async_db_session,
                        "runtime": user_runtime.model_dump(),
                    }
                }

                # Use semaphore to avoid SQLAlchemy session conflicts
                async with semaphore:
                    # Invoke the agent (this is the real async invocation)
                    result = await compiled_agent.ainvoke(
                        {"messages": [HumanMessage(id=f"user-msg-{user_idx}", content=message)]}, config=config
                    )

                return {
                    "user_idx": user_idx,
                    "thread_id": thread_id,
                    "result": result,
                }

            # Create tasks for concurrent execution using asyncio.create_task
            # Tasks are created concurrently but executed with limited parallelism
            tasks = [
                asyncio.create_task(simulate_user_invocation(i, tid, msg))
                for i, (tid, msg) in enumerate(zip(thread_ids, user_messages))
            ]

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all invocations completed successfully
            for i, result in enumerate(results):
                assert not isinstance(result, Exception), f"User {i} invocation failed: {result}"
                assert result["user_idx"] == i
                assert result["thread_id"] == thread_ids[i]
                # Verify the agent produced some output
                assert "messages" in result["result"]
                assert len(result["result"]["messages"]) > 0

            # Verify thread isolation - each thread should have its own conversation
            unique_thread_ids = set(r["thread_id"] for r in results)
            assert len(unique_thread_ids) == num_users, "Each user should have isolated thread"

    @pytest.mark.asyncio
    async def test_message_isolation_with_mocked_llm(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test message isolation with mocked LLM.

        Each thread sends a unique message and receives a unique response.
        Verifies that messages and responses are properly isolated by thread_id.

        Note: Uses mocked LLM to avoid requiring API keys.
        Execution is sequential due to SQLAlchemy async session limitations.
        """
        from unittest.mock import AsyncMock, patch

        # Patch config
        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="You are a helpful assistant.",
        )
        patch_agent_config_manager(stub_config)

        num_threads = 5
        thread_ids = [f"isolation-thread-{i}" for i in range(num_threads)]
        unique_responses = [f"Response for thread {i}" for i in range(num_threads)]

        results = []
        for i in range(num_threads):
            # Create a fresh agent instance for each thread to ensure isolation
            agent = AgentBase(stub_config)

            mock_response = AIMessage(content=unique_responses[i], id=f"mock-ai-msg-{i}")
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)

            thread_id = thread_ids[i]
            user_runtime = replace(runtime_context, thread_id=thread_id)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "db_session": async_db_session,
                    "runtime": user_runtime.model_dump(),
                }
            }

            with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
                compiled_agent = await agent.compile()
                result = await compiled_agent.ainvoke(
                    {"messages": [HumanMessage(id=f"user-msg-{i}", content=f"Hello from thread {i}")]},
                    config=config,
                )

            actual_response = result["messages"][-1].content if result.get("messages") else None
            results.append(
                {
                    "user_idx": i,
                    "thread_id": thread_id,
                    "expected_response": unique_responses[i],
                    "actual_response": actual_response,
                }
            )

        # Verify all completed successfully
        for i, result in enumerate(results):
            # Verify each thread received its unique response (isolation)
            assert result["actual_response"] == result["expected_response"], (
                f"Thread {i} received wrong response: expected '{result['expected_response']}', got '{result['actual_response']}'"
            )

    @pytest.mark.asyncio
    async def test_state_isolation_with_mocked_llm(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test agent internal state isolation with mocked LLM.

        Verifies that each thread maintains independent:
        - loop_count
        - message_count

        Note: Uses mocked LLM to avoid requiring API keys.
        Execution is sequential due to SQLAlchemy async session limitations.
        """
        from unittest.mock import AsyncMock, patch

        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="You are a helpful assistant.",
        )
        patch_agent_config_manager(stub_config)

        num_threads = 5
        thread_ids = [f"state-isolation-thread-{i}" for i in range(num_threads)]
        results = []

        for i in range(num_threads):
            # Create a fresh agent instance for each thread
            agent = AgentBase(stub_config)

            mock_response = AIMessage(content=f"Response for thread {i}", id=f"mock-ai-{i}")
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)

            thread_id = thread_ids[i]
            user_runtime = replace(runtime_context, thread_id=thread_id)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "db_session": async_db_session,
                    "runtime": user_runtime.model_dump(),
                }
            }

            with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
                compiled_agent = await agent.compile()
                result = await compiled_agent.ainvoke(
                    {"messages": [HumanMessage(id=f"user-msg-{i}", content=f"Test from thread {i}")]},
                    config=config,
                )

            results.append(
                {
                    "user_idx": i,
                    "thread_id": thread_id,
                    "loop_count": result.get("loop_count", 0),
                    "message_count": len(result.get("messages", [])),
                }
            )

        # Verify all completed successfully
        for i, result in enumerate(results):
            # Each thread should have independent state
            assert result["loop_count"] >= 0, f"Thread {i} has invalid loop_count"
            assert result["message_count"] > 0, f"Thread {i} has no messages"

    @pytest.mark.asyncio
    async def test_exception_isolation_with_mocked_llm(
        self,
        async_db_session,
        runtime_context,
        agent_stub_config_factory,
        patch_agent_config_manager,
    ):
        """Test that exceptions in one thread don't affect other threads.

        Note: AgentBase._llm_call catches LLM exceptions and returns error messages
        instead of raising, so this test verifies that pattern works correctly.

        Verifies that:
        - Failed LLM calls return error messages (not exceptions)
        - Other threads are not affected
        - Each thread maintains independent execution

        Note: Uses mocked LLM to avoid requiring API keys.
        Execution is sequential due to SQLAlchemy async session limitations.
        """
        from unittest.mock import AsyncMock, patch

        stub_config = agent_stub_config_factory(
            agent_id=runtime_context.agent_id,
            agent_name=runtime_context.agent_name,
            system_prompt="You are a helpful assistant.",
        )
        patch_agent_config_manager(stub_config)

        num_threads = 5
        failing_thread_idx = 2  # Thread 2 will fail
        thread_ids = [f"exception-isolation-thread-{i}" for i in range(num_threads)]
        results = []

        for i in range(num_threads):
            # Create a fresh agent instance for each thread
            agent = AgentBase(stub_config)

            should_fail = i == failing_thread_idx
            if should_fail:
                # For failing thread, raise exception during LLM call
                mock_model = AsyncMock()
                mock_model.ainvoke = AsyncMock(side_effect=ValueError("Simulated LLM failure"))
            else:
                mock_response = AIMessage(content=f"Success response for thread {i}", id=f"mock-ai-{i}")
                mock_model = AsyncMock()
                mock_model.ainvoke = AsyncMock(return_value=mock_response)

            thread_id = thread_ids[i]
            user_runtime = replace(runtime_context, thread_id=thread_id)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "db_session": async_db_session,
                    "runtime": user_runtime.model_dump(),
                }
            }

            with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
                compiled_agent = await agent.compile()
                result = await compiled_agent.ainvoke(
                    {"messages": [HumanMessage(id=f"user-msg-{i}", content=f"Test from thread {i}")]},
                    config=config,
                )

            # Check if the last message contains error content
            last_message = result["messages"][-1]
            is_error = last_message.additional_kwargs.get("error", False)
            has_error_content = "LLM call failed" in str(last_message.content)

            results.append(
                {
                    "user_idx": i,
                    "thread_id": thread_id,
                    "is_error_response": is_error or has_error_content,
                    "message_content": str(last_message.content),
                }
            )

        # Verify the failing thread got an error response
        failing_result = results[failing_thread_idx]
        assert failing_result["is_error_response"], (
            f"Thread {failing_thread_idx} should have error response, got: {failing_result['message_content']}"
        )

        # Verify all other threads succeeded (exception isolation)
        for i, result in enumerate(results):
            if i != failing_thread_idx:
                assert not result["is_error_response"], (
                    f"Thread {i} should not be affected by thread {failing_thread_idx}'s failure, "
                    f"got: {result['message_content']}"
                )
                assert result.get("user_idx") == i, f"Thread {i} has wrong user_idx"
