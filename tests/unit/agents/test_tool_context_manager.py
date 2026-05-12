"""Test track_tool_context for real-world tool tracking."""

import pytest
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.context import (
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
)
from apps.tenant_app_service.agents.metrics import tool_call_tracker
from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage


@pytest.fixture
def runtime_context() -> AgentRuntimeContext:
    """Create test runtime context."""
    return AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=1,
            tenant_name="test_tenant",
            config={},
        ),
        user=AgentUserContext(
            user_id=123,
            username="testuser",
            role="admin",
            tenant_id=1,
            tenant_name="test_tenant",
        ),
        agent_id=1,
        agent_name="test_agent",
        thread_id="thread_test_123",
        session_id="session_test_456",
    )


@pytest.fixture
def runnable_config(runtime_context: AgentRuntimeContext) -> RunnableConfig:
    """Create test RunnableConfig with runtime context."""
    return RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
        }
    )


@pytest.fixture(autouse=True)
def cleanup_storage():
    """Clean up storage before each test."""
    storage = get_storage("memory")
    if hasattr(storage, "_events"):
        storage._events.clear()
    if hasattr(storage, "_session_to_thread"):
        storage._session_to_thread.clear()
    yield
    if hasattr(storage, "_events"):
        storage._events.clear()
    if hasattr(storage, "_session_to_thread"):
        storage._session_to_thread.clear()


class TestToolContextManager:
    """Test track_tool_context context manager."""

    @pytest.mark.asyncio
    async def test_tool_tracking_doesnt_break_execution(self, runtime_context: AgentRuntimeContext):
        """Test that tool tracking context manager doesn't break tool execution."""
        tool_name = "search_tool"
        tool_call_id = "call_123"
        tool_args = {"query": "test query"}

        async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context) as tracker:
            # Simulate tool execution
            result = "Search results: ..."
            tracker.record_result(result)

        # Verify execution completed successfully
        # Note: Use ObservabilityService to query metrics in integration tests

    @pytest.mark.asyncio
    async def test_tool_error_doesnt_break_error_handling(self, runtime_context: AgentRuntimeContext):
        """Test that tool error tracking doesn't interfere with error handling."""
        tool_name = "failing_tool"
        tool_call_id = "call_error"
        tool_args = {"param": "value"}

        with pytest.raises(ValueError, match="Tool execution failed"):
            async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context):
                raise ValueError("Tool execution failed")

        # Verify exception was raised correctly
        # Note: Use ObservabilityService to query metrics in integration tests
