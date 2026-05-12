"""Test tool_calls round-trip through database serialization."""

import json
from datetime import datetime

from langchain_core.messages import AIMessage, ToolMessage

from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.memory.conversation_memory_manager import _serialize_additional_kwargs
from apps.tenant_app_service.hitl.domain import HITL_PAYLOAD_TYPE_APPROVAL_REQUEST


def test_openai_tool_calls_roundtrip():
    """Test that OpenAI format tool_calls survive DB round-trip."""
    # OpenAI format: arguments is a JSON string
    msg = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "use_data_analyst",
                        "arguments": '{"task": "list data source"}',  # JSON string
                    },
                }
            ]
        },
    )

    # Step 1: Serialize for DB storage
    kwargs = _serialize_additional_kwargs(msg.additional_kwargs)
    assert kwargs is not None
    assert "tool_calls" in kwargs

    # Step 2: Simulate SQLAlchemy JSON storage (dumps then loads)
    stored_json = json.dumps(kwargs)
    loaded_kwargs = json.loads(stored_json)

    # Step 3: Verify structure is preserved
    assert "tool_calls" in loaded_kwargs
    assert len(loaded_kwargs["tool_calls"]) == 1
    tc = loaded_kwargs["tool_calls"][0]
    assert tc["function"]["name"] == "use_data_analyst"
    assert tc["function"]["arguments"] == '{"task": "list data source"}'  # Still a string
    assert isinstance(tc["function"]["arguments"], str)

    # Step 4: Verify it's valid JSON when parsed
    parsed_args = json.loads(tc["function"]["arguments"])
    assert parsed_args == {"task": "list data source"}

    # Step 5: Reconstruct AIMessage (what _db_message_to_langchain does)
    reconstructed = AIMessage(content="", additional_kwargs=loaded_kwargs)
    assert reconstructed.additional_kwargs["tool_calls"][0]["function"]["arguments"] == ('{"task": "list data source"}')


def test_empty_arguments_edge_case():
    """Test that empty arguments field is handled correctly."""
    msg = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "some_tool",
                        "arguments": "",  # Empty string (potential issue)
                    },
                }
            ]
        },
    )

    # Serialize and round-trip
    kwargs = _serialize_additional_kwargs(msg.additional_kwargs)
    stored_json = json.dumps(kwargs)
    loaded_kwargs = json.loads(stored_json)

    # Empty string should be normalized to "{}" (valid JSON)
    assert loaded_kwargs["tool_calls"][0]["function"]["arguments"] == "{}"

    # Verify it's valid JSON
    parsed = json.loads(loaded_kwargs["tool_calls"][0]["function"]["arguments"])
    assert parsed == {}


def test_list_data_sources_empty_arguments():
    """Test the exact case from user's bug report: list_data_sources with empty arguments."""
    msg = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "function": {
                        "arguments": "",  # Bug: empty string instead of "{}"
                        "name": "list_data_sources",
                    },
                    "id": "toolu_bdrk_0156YMbwgCjKK5jqnuf4kpNJ",
                    "index": 0,
                    "type": "function",
                }
            ]
        },
    )

    # Serialize (should fix the empty string)
    serialized = _serialize_additional_kwargs(msg.additional_kwargs)

    # Verify empty string was normalized to "{}"
    arguments = serialized["tool_calls"][0]["function"]["arguments"]
    assert arguments == "{}", f"Expected '{{}}', got {repr(arguments)}"

    # Verify it's valid JSON that OpenAI can parse
    parsed = json.loads(arguments)
    assert parsed == {}

    # Full round-trip test
    stored_json = json.dumps(serialized)
    loaded_kwargs = json.loads(stored_json)
    final_arguments = loaded_kwargs["tool_calls"][0]["function"]["arguments"]
    assert final_arguments == "{}"
    json.loads(final_arguments)  # Should not raise


def test_langchain_parsed_format_roundtrip():
    """Test LangChain's parsed format (with 'args' dict instead of 'arguments' string)."""
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "use_data_analyst",
                "args": {"task": "list data source"},  # Dict, not JSON string
                "id": "call_abc123",
                "type": "tool_call",
            }
        ],
    )

    # This is the parsed format - args is a dict
    assert isinstance(msg.tool_calls[0]["args"], dict)

    # When saved, if tool_calls not in additional_kwargs, we add it
    kwargs = msg.additional_kwargs or {}
    if "tool_calls" not in kwargs:
        kwargs = {**kwargs, "tool_calls": msg.tool_calls}

    # Serialize
    serialized = _serialize_additional_kwargs(kwargs)

    # Round-trip
    stored_json = json.dumps(serialized)
    loaded_kwargs = json.loads(stored_json)

    # Verify structure
    assert loaded_kwargs["tool_calls"][0]["args"] == {"task": "list data source"}

    # Reconstruct message
    reconstructed = AIMessage(content="", additional_kwargs=loaded_kwargs)
    # LangChain should reconstruct tool_calls attribute from additional_kwargs
    # (via backwards compatibility validator)


def test_anthropic_format_with_chinese_chars():
    """Test Anthropic format with Chinese characters (real-world case)."""
    msg = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "function": {
                        "arguments": '{"query": "产品销量 sales product 2014"}',
                        "name": "search_data_assets",
                    },
                    "id": "toolu_bdrk_01Fd8FSQmpcXGShsnPcR8y1E",
                    "index": 0,
                    "type": "function",
                }
            ]
        },
    )

    # Serialize
    serialized = _serialize_additional_kwargs(msg.additional_kwargs)

    # Verify arguments is still a string
    arguments = serialized["tool_calls"][0]["function"]["arguments"]
    assert isinstance(arguments, str), "arguments should remain a string"

    # Verify it's valid JSON
    parsed = json.loads(arguments)
    assert parsed == {"query": "产品销量 sales product 2014"}

    # Full round-trip
    stored_json = json.dumps(serialized)
    loaded_kwargs = json.loads(stored_json)

    # After round-trip, arguments should still be parseable
    final_arguments = loaded_kwargs["tool_calls"][0]["function"]["arguments"]
    assert isinstance(final_arguments, str)
    final_parsed = json.loads(final_arguments)
    assert final_parsed == {"query": "产品销量 sales product 2014"}


def test_invalid_arguments_detection():
    """Test that invalid arguments strings are detected and normalized."""
    # Case 1: Empty string -> should be normalized to "{}"
    msg1 = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "function": {"arguments": "", "name": "test"},
                    "id": "call_1",
                    "type": "function",
                }
            ]
        },
    )
    serialized1 = _serialize_additional_kwargs(msg1.additional_kwargs)
    # Empty string should be normalized to valid JSON
    assert serialized1["tool_calls"][0]["function"]["arguments"] == "{}"

    # Case 2: Malformed JSON in arguments (left as-is, OpenAI will reject it)
    msg2 = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "function": {
                        "arguments": "{invalid json}",  # Not valid JSON
                        "name": "test",
                    },
                    "id": "call_2",
                    "type": "function",
                }
            ]
        },
    )
    serialized2 = _serialize_additional_kwargs(msg2.additional_kwargs)
    # Malformed JSON is preserved (will fail at OpenAI level with clear error)
    assert serialized2["tool_calls"][0]["function"]["arguments"] == "{invalid json}"


def _build_agent(agent_stub_config_factory) -> AgentBase:
    stub_config = agent_stub_config_factory(
        agent_id=999,
        agent_name="Test Agent",
        model_key="default-model",
        system_prompt="test prompt",
    )
    return AgentBase(stub_config)


def test_handle_hitl_pause_appends_skipped_messages(agent_stub_config_factory):
    """When HITL approval is requested, remaining tool calls are appended as skipped."""
    agent = _build_agent(agent_stub_config_factory)

    tool_message = ToolMessage(
        id="tm-1",
        content="approval required",
        tool_call_id="call-1",
        additional_kwargs={
            "hitl": {
                "type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
                "proposal_id": "proposal-123",
            }
        },
    )
    tool_calls = [
        {"id": "call-1", "name": "tool_a"},
        {"id": "call-2", "name": "tool_b"},
        {"id": "call-3", "name": "tool_c"},
    ]
    results: list[ToolMessage] = []

    blocked = agent._handle_hitl_pause(
        tool_message=tool_message,
        tool_calls=tool_calls,
        idx=0,
        results=results,
    )

    assert blocked is True
    assert len(results) == 2
    assert [msg.tool_call_id for msg in results] == ["call-2", "call-3"]
    assert all(msg.content == "Skipped: Waiting for HITL approval" for msg in results)

    for msg in results:
        timestamp = msg.additional_kwargs.get("timestamp")
        assert isinstance(timestamp, str)
        datetime.fromisoformat(timestamp)


def test_handle_hitl_pause_noop_when_not_approval_request(agent_stub_config_factory):
    """Non-approval HITL payload should not block or append messages."""
    agent = _build_agent(agent_stub_config_factory)

    tool_message = ToolMessage(
        id="tm-2",
        content="not blocked",
        tool_call_id="call-1",
        additional_kwargs={
            "hitl": {
                "type": "approval_result",
                "proposal_id": "proposal-123",
            }
        },
    )
    tool_calls = [
        {"id": "call-1", "name": "tool_a"},
        {"id": "call-2", "name": "tool_b"},
    ]
    results: list[ToolMessage] = []

    blocked = agent._handle_hitl_pause(
        tool_message=tool_message,
        tool_calls=tool_calls,
        idx=0,
        results=results,
    )

    assert blocked is False
    assert results == []
