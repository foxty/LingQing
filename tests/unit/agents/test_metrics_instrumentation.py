"""Tests for V3 metrics instrumentation on AgentBase."""

import pytest


@pytest.mark.asyncio
async def test_llm_tracker_persists_prompt_context_stats(runtime_context, monkeypatch):
    """LLM tracker should persist prompt-context stats into event context."""
    from langchain_core.messages import AIMessage

    from apps.tenant_app_service.agents.domain import PromptContextStats
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import llm_call_tracker
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    memory_storage._events.clear()
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    prompt_context_stats = PromptContextStats(
        original_count=12,
        sanitized_count=1,
        trimmed_count=3,
        compressed_transient=2,
        compressed_chars_saved=88,
        final_count=9,
    )

    async with llm_call_tracker(
        "test_model",
        runtime_context,
        prompt_context_stats=prompt_context_stats,
    ) as tracker:
        tracker.record_response(
            AIMessage(
                content="ok",
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            )
        )

    events = memory_storage._events.get(runtime_context.session_id, [])
    assert len(events) == 1
    event = events[0]

    assert event.context.message_count == 9
    assert "message_prep" in event.extra_context
    assert event.extra_context["message_prep"]["final_count"] == 9
    assert event.extra_context["message_prep"]["compressed_chars_saved"] == 88


@pytest.mark.asyncio
async def test_tool_context_stores_preview_in_extra_context(runtime_context, monkeypatch):
    """Test that track_tool_context stores tool input/output in extra_context."""
    # Force instrumentation to use memory storage
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
        tool_call_tracker,
    )

    tool_name = "test_tool"
    tool_call_id = "call_123"
    tool_args = {"query": "test query", "limit": 10}

    # Use the context manager to track tool execution
    async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context) as tracker:
        result = {"data": "test result"}
        tracker.record_result(result)

    # Verify event was stored
    session_id = runtime_context.session_id
    events = memory_storage._events.get(session_id, [])

    assert len(events) == 1
    event = events[0]

    # Verify extra_context contains tool previews
    assert "tool_input_preview" in event.extra_context
    assert "tool_output_preview" in event.extra_context
    assert "tool_input_size" in event.extra_context
    assert "tool_output_size" in event.extra_context

    # Verify preview content
    assert "test query" in event.extra_context["tool_input_preview"]
    assert "test result" in event.extra_context["tool_output_preview"]


@pytest.mark.asyncio
async def test_preview_respects_max_length_config(runtime_context, monkeypatch):
    """Test that preview truncation respects METRICS_PREVIEW_MAX_LENGTH config."""
    # Force instrumentation to use memory storage
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    # Mock _truncate_preview to enforce max_length=10
    monkeypatch.setattr(
        agent_metrics_instrumentation,
        "_truncate_preview",
        lambda content, max_length=None: content[:10] if len(content) > 10 else content,
    )

    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
        tool_call_tracker,
    )

    tool_name = "test_tool"
    tool_call_id = "call_123"
    tool_args = {"query": "a" * 100}  # 100 characters

    async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context) as tracker:
        result = {"data": "b" * 100}  # 100 characters
        tracker.record_result(result)

    # Verify truncation
    session_id = runtime_context.session_id
    events = memory_storage._events.get(session_id, [])

    event = events[0]
    assert len(event.extra_context["tool_input_preview"]) <= 10
    assert len(event.extra_context["tool_output_preview"]) <= 10
    # But original sizes are stored
    assert event.extra_context["tool_input_size"] > 10
    assert event.extra_context["tool_output_size"] > 10


@pytest.mark.asyncio
async def test_preview_disabled_when_config_zero(runtime_context, monkeypatch):
    """Test that preview is disabled when METRICS_PREVIEW_MAX_LENGTH is 0."""
    # Force instrumentation to use memory storage
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    # Mock _truncate_preview to return empty string (disabled)
    monkeypatch.setattr(
        agent_metrics_instrumentation,
        "_truncate_preview",
        lambda content, max_length=None: "",
    )

    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
        tool_call_tracker,
    )

    tool_name = "test_tool"
    tool_call_id = "call_123"
    tool_args = {"query": "test"}

    async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context) as tracker:
        result = {"data": "result"}
        tracker.record_result(result)

    # Verify no preview in extra_context
    session_id = runtime_context.session_id
    events = memory_storage._events.get(session_id, [])

    event = events[0]
    assert "tool_input_preview" not in event.extra_context
    assert "tool_output_preview" not in event.extra_context


@pytest.mark.asyncio
async def test_tool_input_serialized_as_json(runtime_context, monkeypatch):
    """Test that tool input is serialized as JSON when possible."""
    # Force instrumentation to use memory storage
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
        tool_call_tracker,
    )

    tool_name = "test_tool"
    tool_call_id = "call_123"
    # Complex nested structure
    tool_args = {
        "query": "test query",
        "filters": {"status": "active", "priority": [1, 2, 3]},
        "limit": 10,
        "nested": {"data": {"value": 123}},
    }

    async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context) as tracker:
        result = {"success": True, "data": [{"id": 1, "name": "test"}]}
        tracker.record_result(result)

    # Verify JSON serialization
    session_id = runtime_context.session_id
    events = memory_storage._events.get(session_id, [])

    assert len(events) == 1
    event = events[0]

    # Verify input is valid JSON
    import json

    input_preview = event.extra_context["tool_input_preview"]
    parsed_input = json.loads(input_preview)
    assert parsed_input["query"] == "test query"
    assert parsed_input["filters"]["status"] == "active"
    assert parsed_input["limit"] == 10

    # Verify output is valid JSON
    output_preview = event.extra_context["tool_output_preview"]
    parsed_output = json.loads(output_preview)
    assert parsed_output["success"] is True
    assert len(parsed_output["data"]) == 1


@pytest.mark.asyncio
async def test_tool_input_fallback_to_str(runtime_context, monkeypatch):
    """Test that tool input falls back to str() when JSON serialization fails."""
    # Force instrumentation to use memory storage
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
        tool_call_tracker,
    )

    # Create an object that can't be JSON serialized
    class NonSerializable:
        def __str__(self):
            return "NonSerializable object"

    tool_name = "test_tool"
    tool_call_id = "call_123"
    tool_args = {"obj": NonSerializable()}

    async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime_context) as tracker:
        result = NonSerializable()
        tracker.record_result(result)

    # Verify fallback to str()
    session_id = runtime_context.session_id
    events = memory_storage._events.get(session_id, [])

    assert len(events) == 1
    event = events[0]

    # Input should contain the string representation
    input_preview = event.extra_context["tool_input_preview"]
    assert "NonSerializable object" in input_preview

    # Output should also contain the string representation
    output_preview = event.extra_context["tool_output_preview"]
    assert "NonSerializable object" in output_preview


@pytest.mark.asyncio
async def test_tool_tracker_record_error_persists_error_status(runtime_context, monkeypatch):
    """Explicit record_error should persist TOOL_CALL with error status."""
    from apps.shared.observability.domain import CallStatus
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import tool_call_tracker

    async with tool_call_tracker("test_tool", "call_456", {"query": "demo"}, runtime_context) as tracker:
        tracker.record_error(RuntimeError("Business failure"))

    events = memory_storage._events.get(runtime_context.session_id, [])
    assert len(events) == 1
    event = events[0]
    assert event.status == CallStatus.ERROR
    assert event.error_message == "Business failure"
