"""Test session lifecycle events (SESSION_START/END)."""

import asyncio

import pytest
from langchain_core.messages import AIMessage

from apps.tenant_app_service.agents.domain import AgentRuntimeContext
from apps.tenant_app_service.agents.metrics import (
    llm_call_tracker,
    record_session_end,
    record_session_start,
    session_tracker,
)


class TestSessionLifecycle:
    """Test SESSION_START and SESSION_END events."""

    @pytest.mark.asyncio
    async def test_session_lifecycle_doesnt_break_execution(
        self,
        runtime_context: AgentRuntimeContext,  # from global conftest.py fixture
    ):
        """Test that session lifecycle tracking doesn't break agent execution."""
        # Record session start

        await record_session_start(runtime_context)

        # Simulate some work with LLM calls
        async def mock_llm_call():
            await asyncio.sleep(0.05)  # 50ms
            async with llm_call_tracker("test_model", runtime_context) as tracker:
                response = AIMessage(
                    content="Test response",
                    usage_metadata={
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "total_tokens": 30,
                    },
                )
                tracker.record_response(response)

        await mock_llm_call()
        await asyncio.sleep(0.05)  # Gap between calls
        await mock_llm_call()

        # Record session end
        await record_session_end(runtime_context)

        # Verify execution completed successfully
        # Note: Use ObservabilityService to query metrics in integration tests

    @pytest.mark.asyncio
    async def test_session_tracker_context_manager(self, runtime_context: AgentRuntimeContext):
        """Test session_tracker context manager properly tracks session lifecycle."""

        # Use context manager for automatic session tracking
        async with session_tracker(runtime_context):
            # Simulate some work with LLM calls
            async def mock_llm_call():
                await asyncio.sleep(0.05)  # 50ms
                async with llm_call_tracker("test_model", runtime_context) as tracker:
                    response = AIMessage(
                        content="Test response",
                        usage_metadata={
                            "input_tokens": 10,
                            "output_tokens": 20,
                            "total_tokens": 30,
                        },
                    )
                    tracker.record_response(response)

            await mock_llm_call()
            await asyncio.sleep(0.05)  # Gap between calls
            await mock_llm_call()

        # Verify execution completed successfully
        # SESSION_END is automatically recorded when exiting context manager

    @pytest.mark.asyncio
    async def test_session_tracker_handles_exceptions(
        self,
        runtime_context: AgentRuntimeContext,  # from global conftest.py fixture
    ):
        """Test session_tracker properly records SESSION_END even on exceptions."""

        # Verify that session_tracker handles exceptions gracefully
        with pytest.raises(ValueError, match="Test error"):
            async with session_tracker(runtime_context):
                # Simulate some work
                await asyncio.sleep(0.01)
                # Raise an exception
                raise ValueError("Test error")

        # SESSION_END should still be recorded despite the exception
