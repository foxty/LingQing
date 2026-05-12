"""Unit tests for token counter."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from apps.tenant_app_service.agents.token_counter import count_tokens


class TestCountMessageTokens:
    """Test token counting functionality."""

    def test_empty_messages_list(self):
        """Test counting tokens with empty message list."""
        assert count_tokens([]) == 0

    def test_human_message_with_content(self):
        """Test counting tokens in HumanMessage with content."""
        messages = [HumanMessage(content="Hello world")]
        # "Hello world" = 11 chars → 11 // 4 = 2 tokens
        assert count_tokens(messages) == 2

    def test_ai_message_with_content(self):
        """Test counting tokens in AIMessage with content."""
        messages = [AIMessage(content="This is a test response from AI")]
        # 31 chars → 7 tokens (31 // 4 = 7)
        assert count_tokens(messages) == 7

    def test_system_message_with_content(self):
        """Test counting tokens in SystemMessage with content."""
        messages = [SystemMessage(content="You are a helpful assistant")]
        # 27 chars → 6 tokens
        assert count_tokens(messages) == 6

    def test_ai_message_with_tool_calls_no_content(self):
        """Test counting tokens in AIMessage with tool_calls but no content."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_weather",
                        "args": {"location": "San Francisco"},
                        "id": "call_123",
                        "type": "tool_call",
                    }
                ],
            )
        ]
        # Empty content (0) + tool_calls JSON
        token_count = count_tokens(messages)
        # Tool calls JSON is ~100 chars → ~25 tokens
        assert token_count > 20  # Should count tool_calls

    def test_ai_message_with_tool_calls_and_content(self):
        """Test counting tokens in AIMessage with both content and tool_calls."""
        messages = [
            AIMessage(
                content="I'll check the weather for you",
                tool_calls=[
                    {
                        "name": "get_weather",
                        "args": {"location": "San Francisco"},
                        "id": "call_123",
                        "type": "tool_call",
                    }
                ],
            )
        ]
        token_count = count_tokens(messages)
        # Content (31 chars → 7 tokens) + tool_calls (~100 chars → 25 tokens) = ~32 tokens
        assert token_count > 30

    def test_tool_message_with_content(self):
        """Test counting tokens in ToolMessage."""
        messages = [
            ToolMessage(
                content="The weather in San Francisco is 65°F and sunny",
                tool_call_id="call_123",
            )
        ]
        token_count = count_tokens(messages)
        # Content (47 chars) + tool_call_id (8 chars) = 55 chars → 13 tokens
        assert token_count == 13

    def test_multiple_messages(self):
        """Test counting tokens across multiple messages."""
        messages = [
            HumanMessage(content="What is the weather?"),  # 20 chars
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_weather",
                        "args": {"location": "NYC"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),  # ~80 chars
            ToolMessage(content="It's 70°F in NYC", tool_call_id="call_1"),  # 16 + 6 = 22 chars
            AIMessage(content="The weather in NYC is 70°F"),  # 27 chars
        ]
        token_count = count_tokens(messages)
        # Total: 20 + 80 + 22 + 27 = ~149 chars → ~37 tokens
        assert token_count > 30

    def test_additional_kwargs_are_counted(self):
        """Test that substantial additional_kwargs are counted."""
        messages = [
            AIMessage(
                content="Result",
                additional_kwargs={
                    "model": "gpt-4",
                    "finish_reason": "stop",
                    "extra_data": "x" * 200,  # Large field
                },
            )
        ]
        token_count = count_tokens(messages)
        # Content (6 chars) + additional_kwargs (~220 chars) = ~226 chars → ~56 tokens
        assert token_count > 50

    def test_additional_kwargs_mixed_fields(self):
        """Test that only substantial fields in additional_kwargs are counted."""
        messages = [
            AIMessage(
                content="Result",
                additional_kwargs={
                    "timestamp": "2025-12-22T10:00:00Z",  # Excluded
                    "session_id": "session_123",  # Excluded
                    "tool_calls": [{"name": "test"}],  # Included
                    "model_info": {"model": "claude", "version": "3"},  # Included
                },
            )
        ]
        token_count = count_tokens(messages)
        # Content (6) + tool_calls + model_info JSON (~60 chars) = ~66 chars → ~16 tokens
        assert token_count > 10

    def test_chinese_characters(self):
        """Test token counting with Chinese characters."""
        messages = [
            HumanMessage(content="找出2014年销冠军产品"),  # 12 Chinese chars
        ]
        token_count = count_tokens(messages)
        # Chinese chars are counted as chars, ~12 chars → 3 tokens
        assert token_count == 3

    def test_complex_tool_calls_with_nested_args(self):
        """Test counting tokens with complex nested tool call arguments."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_sql_query",
                        "args": {
                            "data_source_id": 2,
                            "sql_query": "SELECT * FROM orders WHERE year = 2014 AND product_id IN (1, 2, 3)",
                        },
                        "id": "call_abc123",
                        "type": "tool_call",
                    }
                ],
            )
        ]
        token_count = count_tokens(messages)
        # Complex tool_calls JSON (~150 chars) → ~37 tokens
        assert token_count > 35

    def test_message_without_content_attribute(self):
        """Test handling messages without content attribute."""

        # Edge case: message-like object without content
        class CustomMessage:
            pass

        # Should not crash, should handle gracefully
        token_count = count_tokens([CustomMessage()])
        assert token_count == 0

    def test_empty_string_content(self):
        """Test handling empty string content."""
        messages = [HumanMessage(content="")]
        token_count = count_tokens(messages)
        assert token_count == 0

    def test_empty_tool_calls_list(self):
        """Test handling empty tool_calls list."""
        messages = [AIMessage(content="Result", tool_calls=[])]
        token_count = count_tokens(messages)
        # Only content counted (6 chars → 1 token)
        assert token_count == 1

    def test_empty_additional_kwargs(self):
        """Test handling empty additional_kwargs."""
        messages = [AIMessage(content="Result", additional_kwargs={})]
        token_count = count_tokens(messages)
        # Only content counted (6 chars → 1 token)
        assert token_count == 1

    def test_realistic_conversation_scenario(self):
        """Test realistic conversation with mix of message types."""
        messages = [
            SystemMessage(content="You are a helpful data analyst assistant"),
            HumanMessage(content="找出2014年销冠军产品以及其月销量趋势"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "use_data_analyst",
                        "args": {"task": "找出2014年销冠军产品以及其月销量趋势"},
                        "id": "toolu_bdrk_01BZn6Fvz647Xw4ZhaY84zvS",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content="完成！以下是2014年销售冠军产品的分析结果：\n\n## 🏆 2014年销售冠军产品\n\n### 产品信息\n\n**The Original Mr. Fuzzy**",
                tool_call_id="toolu_bdrk_01BZn6Fvz647Xw4ZhaY84zvS",
            ),
            AIMessage(content="根据数据分析结果，2014年的销售冠军产品是 The Original Mr. Fuzzy..."),
        ]
        token_count = count_tokens(messages)
        # System prompt (~40 chars) + user msg (~18 chars) + tool_calls (~100 chars) +
        # tool result (~60 chars + tool_call_id 36 chars) + AI response (~40 chars)
        # Total: ~294 chars → ~73 tokens
        assert token_count > 70
        assert token_count < 100  # Reasonable upper bound

    def test_token_count_comparison_old_vs_new(self):
        """Test that new counter counts more tokens than old approach."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "complex_tool",
                        "args": {"param1": "value1", "param2": "value2"},
                        "id": "call_123",
                        "type": "tool_call",
                    }
                ],
            )
        ]

        # Old approach (content only)
        old_count = sum(len(msg.content) for msg in messages if hasattr(msg, "content")) // 4

        # New approach
        new_count = count_tokens(messages)

        # New counter should count more due to tool_calls
        assert new_count > old_count
        assert old_count == 0  # Content is empty
        assert new_count > 20  # Tool calls add significant tokens
