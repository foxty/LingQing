"""Tests for JSON serialization of additional_kwargs with non-serializable objects."""

import json

from langchain_core.messages import AIMessage, HumanMessage

from apps.tenant_app_service.agents.memory.conversation_memory_manager import _serialize_additional_kwargs


class TestSerializeAdditionalKwargs:
    """Test serialization of additional_kwargs to handle non-JSON-serializable objects."""

    def test_empty_kwargs(self):
        """Test that empty kwargs returns empty dict."""
        result = _serialize_additional_kwargs(None)
        assert result is None

        result = _serialize_additional_kwargs({})
        assert result == {}

    def test_normal_serializable_kwargs(self):
        """Test that normal serializable kwargs are returned as-is."""
        kwargs = {
            "timestamp": "2025-12-21T09:41:30.319000",
            "session_id": "session-123",
            "number": 42,
            "nested": {"key": "value"},
        }
        result = _serialize_additional_kwargs(kwargs)
        assert result == kwargs
        # Verify it's JSON serializable
        json.dumps(result)

    def test_message_object_in_kwargs(self):
        """Test that LangChain message objects in kwargs are converted to strings."""
        # Create a message object
        msg = HumanMessage(content="test message")

        kwargs = {
            "timestamp": "2025-12-21T09:41:30.319000",
            "embedded_message": msg,  # Non-serializable
        }

        result = _serialize_additional_kwargs(kwargs)

        # The embedded_message should be converted to string
        assert isinstance(result["embedded_message"], str)
        assert "test message" in result["embedded_message"]

        # Verify the result is JSON serializable
        json.dumps(result)

    def test_multiple_non_serializable_values(self):
        """Test that multiple non-serializable values are handled."""
        msg1 = HumanMessage(content="msg1")
        msg2 = AIMessage(content="msg2")

        kwargs = {
            "msg1": msg1,
            "msg2": msg2,
            "normal": "value",
        }

        result = _serialize_additional_kwargs(kwargs)

        # Non-serializable values should be strings
        assert isinstance(result["msg1"], str)
        assert isinstance(result["msg2"], str)
        # Normal value should be unchanged
        assert result["normal"] == "value"

        # Verify JSON serializable
        json.dumps(result)

    def test_complex_nested_structure(self):
        """Test nested structures with non-serializable objects."""
        msg = HumanMessage(content="test")

        kwargs = {
            "nested": {
                "message": msg,
                "value": 42,
            },
            "list": [1, 2, 3],
        }

        result = _serialize_additional_kwargs(kwargs)

        # The nested message should be converted to string
        # Note: This depends on the depth of nested structures
        # For now, the function handles top-level non-serializable values

        # Verify JSON serializable at top level
        json.dumps(result)

    def test_custom_object_conversion(self):
        """Test that custom objects are converted to string representation."""

        class CustomObject:
            def __str__(self):
                return "CustomObject()"

        obj = CustomObject()
        kwargs = {"obj": obj}

        result = _serialize_additional_kwargs(kwargs)

        assert result["obj"] == "CustomObject()"
        json.dumps(result)

    def test_preserves_critical_fields(self):
        """Test that critical fields like 'arguments' and 'tool_call_id' are preserved."""
        msg = HumanMessage(content="test message")

        kwargs = {
            "arguments": '{"key": "value"}',  # Must remain as JSON string
            "tool_call_id": "call-123",  # Must remain as-is
            "embedded_message": msg,  # Should be converted to string
            "timestamp": "2025-12-21T09:41:30",
        }

        result = _serialize_additional_kwargs(kwargs)

        # Critical fields should be unchanged
        assert result["arguments"] == '{"key": "value"}'
        assert result["tool_call_id"] == "call-123"
        # Non-critical field with non-serializable object should be string
        assert isinstance(result["embedded_message"], str)
        # Normal field should be unchanged
        assert result["timestamp"] == "2025-12-21T09:41:30"

        # Entire result should be JSON serializable
        json.dumps(result)


def test_ai_message_tool_calls_already_dicts():
    """Test that AIMessage.tool_calls are already dicts and JSON-serializable."""
    from langchain_core.messages import AIMessage

    # Create an AIMessage with tool_calls (LangChain stores them as dicts)
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "test_tool",
                "args": {"param": "value"},
                "id": "test-call-id",
                "type": "tool_call",
            }
        ],
    )

    # Verify tool_calls are already dicts
    assert isinstance(msg.tool_calls, list)
    assert isinstance(msg.tool_calls[0], dict)

    # They should be JSON serializable as-is
    json.dumps(msg.tool_calls)

    # Verify structure is preserved
    assert msg.tool_calls[0]["name"] == "test_tool"
    assert msg.tool_calls[0]["args"] == {"param": "value"}
    assert msg.tool_calls[0]["id"] == "test-call-id"
