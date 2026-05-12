"""Tests for system prompt token counting."""

from langchain_core.messages import AIMessage, HumanMessage

from apps.tenant_app_service.agents.token_counter import count_tokens


class TestSystemPromptTokenCounting:
    """Tests for system prompt inclusion in token counting."""

    def test_count_without_system_prompt(self):
        """Test token counting without system prompt (backward compatibility)."""
        messages = [
            HumanMessage(content="Hello"),  # 5 chars → 1 token
            AIMessage(content="Hi there"),  # 8 chars → 2 tokens
        ]
        token_count = count_tokens(messages)
        assert token_count == 3  # (5 + 8) / 4 = 3

    def test_count_with_system_prompt(self):
        """Test token counting with system prompt."""
        system_prompt = "You are a helpful assistant."  # 29 chars → 7 tokens
        messages = [
            HumanMessage(content="Hello"),  # 5 chars → 1 token
            AIMessage(content="Hi there"),  # 8 chars → 2 tokens
        ]
        token_count = count_tokens(messages, system_prompt=system_prompt)
        # (29 + 5 + 8) / 4 = 10 tokens
        assert token_count == 10

    def test_count_with_empty_system_prompt(self):
        """Test that empty system prompt doesn't affect count."""
        messages = [HumanMessage(content="Test")]  # 4 chars → 1 token

        # Empty string should not add tokens
        token_count_empty = count_tokens(messages, system_prompt="")
        assert token_count_empty == 1

        # None should not add tokens
        token_count_none = count_tokens(messages, system_prompt=None)
        assert token_count_none == 1

    def test_count_with_large_system_prompt(self):
        """Test token counting with large system prompt."""
        # Simulate a large system prompt (500 chars)
        large_prompt = "a" * 500  # 500 chars → 125 tokens
        messages = [
            HumanMessage(content="Hello"),  # 5 chars → 1 token
        ]
        token_count = count_tokens(messages, system_prompt=large_prompt)
        # (500 + 5) / 4 = 126 tokens
        assert token_count == 126

    def test_count_messages_with_system_prompt_real_scenario(self):
        """Test realistic scenario with system prompt and conversation."""
        system_prompt = """You are Agent One, an intelligent enterprise assistant.

## Core Responsibilities
- Understand user intent and extract analysis requirements
- Answer general questions using knowledge base
"""  # ~160 chars → 40 tokens

        messages = [
            HumanMessage(content="分析一下最近的销售数据"),  # 12 chars → 3 tokens
            AIMessage(content="好的，我来帮您分析销售数据。"),  # 15 chars → 3 tokens
        ]

        # Without system prompt
        token_count_no_prompt = count_tokens(messages)
        assert token_count_no_prompt == 6  # (12 + 15) / 4 = 6

        # With system prompt
        token_count_with_prompt = count_tokens(messages, system_prompt=system_prompt)
        assert token_count_with_prompt > 40  # Should include system prompt tokens
        assert token_count_with_prompt == token_count_no_prompt + (len(system_prompt) // 4)
