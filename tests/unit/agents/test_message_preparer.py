"""Tests for MessagePreparer - Message preparation for LLM calls.

This test file verifies that:
1. Message sanitization correctly removes incomplete tool_call/tool_result pairs
2. Orphaned ToolMessages are identified and removed
3. Historical tool outputs can be compressed
4. Complete message preparation for LLM invocation works correctly
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.domain import RETENTION_LONG_LIVED, RETENTION_TRANSIENT
from apps.tenant_app_service.agents.message_preparer import TRANSIENT_COMPRESS_MAX_CHARS, MessagePreparer


class TestMessagePreparer:
    """Test MessagePreparer functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.preparer = MessagePreparer("test_agent")

    def _create_ai_message_with_tools(self, tool_names: list[str]) -> AIMessage:
        """Helper to create AIMessage with tool calls.

        Args:
            tool_names: List of tool names to create tool calls for

        Returns:
            AIMessage with tool_calls
        """
        tool_calls = [
            {
                "id": f"call_{tool_name}_{i}",
                "name": tool_name,
                "args": {"arg": f"value_{i}"},
            }
            for i, tool_name in enumerate(tool_names)
        ]
        return AIMessage(content="Need to use tools", tool_calls=tool_calls)

    def _create_tool_message(self, tool_call_id: str, content: str = "Tool result") -> ToolMessage:
        """Helper to create ToolMessage.

        Args:
            tool_call_id: ID of the tool call this message responds to
            content: Message content

        Returns:
            ToolMessage instance
        """
        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            additional_kwargs={"timestamp": "2024-01-01T00:00:00Z"},
        )


class TestSanitizeMessages(TestMessagePreparer):
    """Test message sanitization."""

    def test_sanitize_complete_tool_call_sequence(self) -> None:
        """Test that complete tool_call/tool_result pairs are preserved."""
        ai_msg = self._create_ai_message_with_tools(["search", "analyze"])
        tool_msg_1 = self._create_tool_message("call_search_0", "Search results")
        tool_msg_2 = self._create_tool_message("call_analyze_1", "Analysis results")

        messages = [ai_msg, tool_msg_1, tool_msg_2]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        assert len(sanitized) == 3
        assert len(removed_ids) == 0
        assert sanitized == messages

    def test_sanitize_removes_incomplete_tool_calls(self) -> None:
        """Test that AIMessage with missing ToolMessages is removed."""
        ai_msg = self._create_ai_message_with_tools(["search", "analyze"])
        # Only provide one result (missing one)
        tool_msg_1 = self._create_tool_message("call_search_0", "Search results")

        messages = [ai_msg, tool_msg_1]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        # AIMessage and its partial tool message should be removed
        assert len(sanitized) == 0
        assert len(removed_ids) == 2
        assert ai_msg.id in removed_ids
        assert tool_msg_1.id in removed_ids

    def test_sanitize_removes_orphaned_tool_messages(self) -> None:
        """Test that ToolMessages without parent AIMessage are removed."""
        text_msg = SystemMessage(content="System message")
        orphaned_tool_msg = self._create_tool_message("call_orphaned_0", "Orphaned result")

        messages = [text_msg, orphaned_tool_msg]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        # Orphaned ToolMessage should be removed
        assert len(sanitized) == 1
        assert sanitized[0] == text_msg
        assert len(removed_ids) == 1
        assert orphaned_tool_msg.id in removed_ids

    def test_sanitize_preserves_non_tool_messages(self) -> None:
        """Test that regular messages are preserved."""
        sys_msg = SystemMessage(content="System prompt")
        ai_msg = AIMessage(content="Regular AI response")
        tool_msg = SystemMessage(content="Another system message")

        messages = [sys_msg, ai_msg, tool_msg]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        assert len(sanitized) == 3
        assert len(removed_ids) == 0
        assert sanitized == messages

    def test_sanitize_empty_messages(self) -> None:
        """Test sanitization of empty message list."""
        messages: list[AIMessage] = []
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        assert len(sanitized) == 0
        assert len(removed_ids) == 0

    def test_sanitize_multiple_incomplete_sequences(self) -> None:
        """Test sanitization with multiple incomplete sequences."""
        # First incomplete sequence
        ai_msg_1 = self._create_ai_message_with_tools(["search"])
        tool_msg_1 = self._create_tool_message("call_search_0", "Result")

        # Complete sequence
        ai_msg_2 = self._create_ai_message_with_tools(["analyze"])
        tool_msg_2 = self._create_tool_message("call_analyze_0", "Analysis")

        # Second incomplete sequence
        ai_msg_3 = self._create_ai_message_with_tools(["plan", "execute"])
        tool_msg_3a = self._create_tool_message("call_plan_0", "Plan result")
        # Missing execute result

        messages = [
            ai_msg_1,
            tool_msg_1,  # complete (has all tool results)
            ai_msg_2,
            tool_msg_2,  # complete (has all tool results)
            ai_msg_3,
            tool_msg_3a,  # incomplete - missing execute result
        ]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        # First two sequences are complete, third is incomplete and should be removed
        assert len(sanitized) == 4
        assert ai_msg_1 in sanitized
        assert tool_msg_1 in sanitized
        assert ai_msg_2 in sanitized
        assert tool_msg_2 in sanitized

    def test_sanitize_non_consecutive_tool_messages(self) -> None:
        """Test that interruption stops tool message collection."""
        ai_msg = self._create_ai_message_with_tools(["search", "analyze"])
        tool_msg_1 = self._create_tool_message("call_search_0", "Search result")
        interrupt_msg = SystemMessage(content="Interruption")
        tool_msg_2 = self._create_tool_message("call_analyze_1", "Analyze result")

        messages = [ai_msg, tool_msg_1, interrupt_msg, tool_msg_2]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        # Incomplete sequence should be removed, interrupt preserved
        assert len(sanitized) == 1
        assert sanitized[0] == interrupt_msg

    def test_sanitize_ai_with_zero_tool_results(self) -> None:
        """AIMessage with tool_calls but no ToolMessages at all is removed."""
        ai_msg = self._create_ai_message_with_tools(["search", "analyze"])
        human = HumanMessage(content="follow up")

        messages = [ai_msg, human]
        sanitized, removed_ids = self.preparer.sanitize_messages(messages)

        assert len(sanitized) == 1
        assert sanitized[0] == human
        assert ai_msg.id in removed_ids

    def test_sanitize_single_complete_tool_call(self) -> None:
        """Simplest happy path: one tool call with its result."""
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._create_tool_message("call_search_0", "result")

        sanitized, removed_ids = self.preparer.sanitize_messages([ai_msg, tool_msg])

        assert len(sanitized) == 2
        assert len(removed_ids) == 0


@pytest.mark.asyncio
class TestPrepareForLLM(TestMessagePreparer):
    """Test complete message preparation for LLM."""

    async def test_prepare_combines_system_and_conversation_messages(self):
        """Test that system messages are prepended to conversation."""
        sys_msg = SystemMessage(content="You are helpful")
        ai_msg = AIMessage(content="Hello")

        system_messages = [sys_msg]
        conversation_messages = [ai_msg]

        result, removed_ids, stats = await self.preparer.prepare_for_llm(
            conversation_messages, system_messages, RunnableConfig()
        )

        # System message should come first
        assert len(result) == 2
        assert result[0] == sys_msg
        assert result[1] == ai_msg
        assert len(removed_ids) == 0
        assert stats.original_count == 1
        assert stats.final_count == 2

    async def test_prepare_sanitizes_messages(self):
        """Test that prepare_for_llm sanitizes messages."""
        ai_msg = self._create_ai_message_with_tools(["search"])
        # Don't provide tool message (incomplete)

        system_messages = [SystemMessage(content="System")]
        conversation_messages = [ai_msg]

        result, removed_ids, stats = await self.preparer.prepare_for_llm(
            conversation_messages, system_messages, RunnableConfig()
        )

        # Incomplete AI message should be removed
        assert len(result) == 1  # Only system message
        assert result[0].content == "System"
        assert ai_msg.id in removed_ids
        assert stats.sanitized_count == 1
        assert stats.sanitized_chars > 0

    async def test_prepare_with_complete_tool_sequence(self):
        """Test prepare_for_llm with complete tool sequences."""
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._create_tool_message("call_search_0", "Results")

        system_messages = [SystemMessage(content="System")]
        conversation_messages = [ai_msg, tool_msg]

        result, removed_ids, stats = await self.preparer.prepare_for_llm(
            conversation_messages, system_messages, RunnableConfig()
        )

        # All messages should be preserved
        assert len(result) == 3
        assert result[0].content == "System"
        assert result[1] == ai_msg
        assert result[2] == tool_msg
        assert len(removed_ids) == 0
        assert stats.sanitized_count == 0
        assert stats.trimmed_count == 0

    async def test_prepare_multiple_system_messages(self):
        """Test prepare_for_llm with multiple system messages."""
        sys_msg_1 = SystemMessage(content="System 1")
        sys_msg_2 = SystemMessage(content="System 2")
        ai_msg = AIMessage(content="Response")

        system_messages = [sys_msg_1, sys_msg_2]
        conversation_messages = [ai_msg]

        result, removed_ids, stats = await self.preparer.prepare_for_llm(
            conversation_messages, system_messages, RunnableConfig()
        )

        # System messages should come first in order
        assert len(result) == 3
        assert result[0] == sys_msg_1
        assert result[1] == sys_msg_2
        assert result[2] == ai_msg
        assert stats.final_count == 3


class TestTrimMessages(TestMessagePreparer):
    """Test message trimming to a fixed window."""

    def setup_method(self):
        """Setup a preparer with a small max_messages limit for easier testing."""
        self.preparer = MessagePreparer("test_agent", max_messages=4)

    def test_trim_no_op_when_under_limit(self):
        """Messages within the limit are returned unchanged."""
        messages = [AIMessage(content=f"msg {i}") for i in range(4)]
        result, dropped = self.preparer.trim_messages(messages)
        assert result == messages
        assert dropped == []

    def test_trim_no_op_when_at_limit(self):
        """Messages exactly at the limit are returned unchanged."""
        messages = [AIMessage(content=f"msg {i}") for i in range(4)]
        result, dropped = self.preparer.trim_messages(messages)
        assert len(result) == 4
        assert dropped == []

    def test_trim_keeps_most_recent_plain_messages(self):
        """When trimming, the most recent messages are kept."""
        messages = [AIMessage(content=f"msg {i}") for i in range(6)]
        result, dropped = self.preparer.trim_messages(messages)
        assert len(result) == 4
        assert result == messages[-4:]
        assert len(dropped) == 2

    def test_trim_preserves_tool_call_group_integrity(self):
        """A tool-call group that would be split is dropped entirely."""
        # Group 1: single plain message
        plain = AIMessage(content="plain")
        # Group 2: AIMessage with 2 tool calls + 2 ToolMessages (size=3)
        ai_with_tools = self._create_ai_message_with_tools(["search", "analyze"])
        tool_1 = self._create_tool_message("call_search_0")
        tool_2 = self._create_tool_message("call_analyze_1")
        # Group 3: another plain message (fits in limit)
        recent = AIMessage(content="recent")

        # With max_messages=4: recent(1) + group2(3) = 4, plain is cut off.
        messages = [plain, ai_with_tools, tool_1, tool_2, recent]
        result, dropped = self.preparer.trim_messages(messages)
        assert len(result) == 4
        assert plain not in result
        assert ai_with_tools in result
        assert tool_1 in result
        assert tool_2 in result
        assert recent in result

    def test_trim_drops_whole_group_when_it_cannot_fit(self):
        """A tool-call group larger than one slot that doesn't fit is dropped as a unit."""
        # With max_messages=4:
        # Group A: ai+2tools = 3 messages
        # Group B: ai+2tools = 3 messages  <- won't fit together with group A
        ai_a = self._create_ai_message_with_tools(["tool_a1", "tool_a2"])
        tm_a1 = self._create_tool_message("call_tool_a1_0")
        tm_a2 = self._create_tool_message("call_tool_a2_1")
        ai_b = self._create_ai_message_with_tools(["tool_b1", "tool_b2"])
        tm_b1 = self._create_tool_message("call_tool_b1_0")
        tm_b2 = self._create_tool_message("call_tool_b2_1")

        messages = [ai_a, tm_a1, tm_a2, ai_b, tm_b1, tm_b2]
        result, dropped = self.preparer.trim_messages(messages)

        # Group B (most recent, size 3) fits. Group A (size 3) would push total
        # to 6 > 4, so it is dropped entirely.
        assert len(result) == 3
        assert ai_b in result
        assert tm_b1 in result
        assert tm_b2 in result
        assert ai_a not in result
        assert len(dropped) == 1

    def test_trim_empty_list(self):
        """Trimming an empty list returns an empty list."""
        result, dropped = self.preparer.trim_messages([])
        assert result == []
        assert dropped == []

    def test_trim_does_not_start_with_tool_message(self):
        """After trimming, the first message is never a dangling ToolMessage."""
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._create_tool_message("call_search_0")
        human = HumanMessage(content="follow-up")
        recent = AIMessage(content="response")

        # With max_messages=4: recent(1)+human(1)+tool_group(2) = 4
        messages = [ai_msg, tool_msg, human, recent]
        result, _dropped = self.preparer.trim_messages(messages)
        assert len(result) == 4
        assert not isinstance(result[0], ToolMessage)

    def test_trim_guarantees_human_message_survives(self):
        """When trimming would drop all HumanMessages, re-include the most recent one."""
        human = HumanMessage(content="user question")
        # Two large tool-call groups that fill the window (3+3=6 > max_messages=4)
        ai_a = self._create_ai_message_with_tools(["t1", "t2"])
        tm_a1 = self._create_tool_message("call_t1_0")
        tm_a2 = self._create_tool_message("call_t2_1")
        ai_b = self._create_ai_message_with_tools(["t3", "t4"])
        tm_b1 = self._create_tool_message("call_t3_0")
        tm_b2 = self._create_tool_message("call_t4_1")

        messages = [human, ai_a, tm_a1, tm_a2, ai_b, tm_b1, tm_b2]
        result, _dropped = self.preparer.trim_messages(messages)

        human_msgs = [m for m in result if isinstance(m, HumanMessage)]
        assert len(human_msgs) >= 1, "At least one HumanMessage must survive trimming"

    def test_trim_no_human_message_anywhere(self):
        """No crash when the entire message list has no HumanMessage (e.g. HITL resume)."""
        messages = [
            AIMessage(content=f"ai {i}") for i in range(6)
        ]
        result, dropped = self.preparer.trim_messages(messages)

        assert len(result) == 4
        assert len(dropped) == 2
        # No HumanMessage to re-include, no error

    def test_trim_single_group_exceeds_limit(self):
        """One tool-call group larger than max_messages: group is dropped, nothing kept."""
        # 1 AI + 4 Tools = 5 messages > max_messages=4
        ai = self._create_ai_message_with_tools(["a", "b", "c", "d"])
        tools = [self._create_tool_message(f"call_{n}_{i}") for i, n in enumerate(["a", "b", "c", "d"])]

        messages = [ai] + tools
        result, dropped = self.preparer.trim_messages(messages)

        # Group can't fit, so nothing is kept
        assert len(result) == 0
        assert len(dropped) == 1

    def test_trim_human_already_in_kept_no_duplicate(self):
        """When HumanMessage is already in the kept window, no duplicate re-include."""
        old_ai = AIMessage(content="old")
        human = HumanMessage(content="question")
        ai = AIMessage(content="answer")
        recent = AIMessage(content="followup")

        messages = [old_ai, human, ai, recent]
        result, _dropped = self.preparer.trim_messages(messages)

        human_msgs = [m for m in result if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 1


@pytest.mark.asyncio
class TestPrepareForLLMWithTrim(TestMessagePreparer):
    """Test that prepare_for_llm applies trimming after sanitization."""

    def setup_method(self):
        self.preparer = MessagePreparer("test_agent", max_messages=3)

    async def test_prepare_trims_after_sanitization(self):
        """Trimming is applied to the sanitized conversation (not system messages)."""
        from langchain_core.messages import HumanMessage

        sys_msg = SystemMessage(content="System")
        msgs = [HumanMessage(content=f"human {i}") for i in range(5)]

        result, removed_ids, stats = await self.preparer.prepare_for_llm(msgs, [sys_msg], RunnableConfig())

        # System message + 3 most-recent conversation messages
        assert len(result) == 4
        assert result[0] == sys_msg
        assert result[1:] == msgs[-3:]
        assert len(removed_ids) == 0
        assert stats.trimmed_count == 2
        assert stats.trimmed_chars == len(msgs[0].content) + len(msgs[1].content)

    async def test_prepare_sanitizes_then_trims(self):
        """Sanitization runs before trimming; trimming operates on the clean list."""
        from langchain_core.messages import HumanMessage

        # Incomplete group at the start (will be sanitized away)
        ai_incomplete = self._create_ai_message_with_tools(["x"])
        # 4 plain messages after it
        plains = [HumanMessage(content=f"h{i}") for i in range(4)]

        result, removed_ids, stats = await self.preparer.prepare_for_llm([ai_incomplete] + plains, [], RunnableConfig())

        # After sanitization: 4 plain messages remain.
        # After trim (max=3): 3 most-recent kept.
        assert len(result) == 3
        assert result == plains[-3:]
        assert ai_incomplete.id in removed_ids
        assert stats.sanitized_count == 1
        assert stats.trimmed_count == 1


class TestCompressAndPreserve(TestMessagePreparer):
    """Test _compress_and_preserve: long-lived preservation and transient truncation."""

    def setup_method(self):
        self.preparer = MessagePreparer("test_agent", max_messages=4)

    def _tool_msg(self, call_id: str, content: str, retention: str = RETENTION_TRANSIENT) -> ToolMessage:
        return ToolMessage(
            content=content,
            tool_call_id=call_id,
            additional_kwargs={
                "result_retention": retention,
                "tool_name": call_id.split("_")[1] if "_" in call_id else "tool",
            },
        )

    def test_long_lived_dropped_group_preserved_as_system_message(self):
        """Long-lived ToolMessages from dropped groups become SystemMessages."""
        long_content = "important spec data"
        dropped_tool = self._tool_msg("call_load_spec_0", long_content, RETENTION_LONG_LIVED)
        ai_msg = self._create_ai_message_with_tools(["load_spec"])
        dropped_groups = [[ai_msg, dropped_tool]]

        kept = [HumanMessage(content="hi"), AIMessage(content="hello")]
        result, preserved_count, _preserved_chars, _compressed_count, _compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, dropped_groups)
        )

        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert "Preserved Tool Output" in result[0].content
        assert long_content in result[0].content
        assert result[1:] == kept
        assert preserved_count == 1

    def test_multiple_long_lived_outputs_combined_into_one_system_message(self):
        """Multiple long-lived ToolMessages from different dropped groups merge into a single SystemMessage."""
        tool_a = self._tool_msg("call_load_spec_0", "spec data", RETENTION_LONG_LIVED)
        ai_a = self._create_ai_message_with_tools(["load_spec"])
        tool_b = self._tool_msg("call_get_app_0", "app data", RETENTION_LONG_LIVED)
        ai_b = self._create_ai_message_with_tools(["get_app"])
        dropped_groups = [[ai_a, tool_a], [ai_b, tool_b]]

        kept = [HumanMessage(content="hi")]
        result, preserved_count, _preserved_chars, _compressed_count, _compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, dropped_groups)
        )

        assert len(result) == 2
        preserved = result[0]
        assert isinstance(preserved, SystemMessage)
        assert "spec data" in preserved.content
        assert "app data" in preserved.content
        assert "load" in preserved.content
        assert "get" in preserved.content
        assert preserved_count == 2

    def test_transient_dropped_group_not_preserved(self):
        """Transient ToolMessages from dropped groups are silently discarded."""
        dropped_tool = self._tool_msg("call_search_0", "search results", RETENTION_TRANSIENT)
        ai_msg = self._create_ai_message_with_tools(["search"])
        dropped_groups = [[ai_msg, dropped_tool]]

        kept = [HumanMessage(content="hi")]
        result, preserved_count, _preserved_chars, _compressed_count, _compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, dropped_groups)
        )

        assert len(result) == 1
        assert result[0].content == "hi"
        assert preserved_count == 0

    def test_old_transient_tool_output_truncated(self):
        """Transient ToolMessages before last HumanMessage are truncated when long."""
        long_content = "x" * (TRANSIENT_COMPRESS_MAX_CHARS + 100)
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._tool_msg("call_search_0", long_content, RETENTION_TRANSIENT)
        human = HumanMessage(content="question")
        recent_ai = AIMessage(content="answer")

        kept = [ai_msg, tool_msg, human, recent_ai]
        result, _preserved_count, _preserved_chars, compressed_count, compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, [])
        )

        truncated = result[1]
        assert isinstance(truncated, ToolMessage)
        assert len(truncated.content) < len(long_content)
        assert truncated.content.endswith("... [truncated]")
        assert compressed_count == 1
        assert compressed_chars_saved > 0

    def test_old_long_lived_tool_output_not_truncated(self):
        """Long-lived ToolMessages in kept messages are never truncated."""
        long_content = "y" * (TRANSIENT_COMPRESS_MAX_CHARS + 100)
        ai_msg = self._create_ai_message_with_tools(["load_spec"])
        tool_msg = self._tool_msg("call_load_spec_0", long_content, RETENTION_LONG_LIVED)
        human = HumanMessage(content="question")

        kept = [ai_msg, tool_msg, human]
        result, _preserved_count, _preserved_chars, compressed_count, compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, [])
        )

        assert result[1].content == long_content
        assert compressed_count == 0
        assert compressed_chars_saved == 0

    def test_recent_transient_tool_output_not_truncated(self):
        """Transient ToolMessages after last HumanMessage are NOT truncated."""
        long_content = "z" * (TRANSIENT_COMPRESS_MAX_CHARS + 100)
        human = HumanMessage(content="question")
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._tool_msg("call_search_0", long_content, RETENTION_TRANSIENT)

        kept = [human, ai_msg, tool_msg]
        result, _preserved_count, _preserved_chars, compressed_count, compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, [])
        )

        assert result[2].content == long_content
        assert compressed_count == 0
        assert compressed_chars_saved == 0

    def test_short_transient_tool_output_not_truncated(self):
        """Transient ToolMessages under the char limit are left as-is."""
        short_content = "brief"
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._tool_msg("call_search_0", short_content, RETENTION_TRANSIENT)
        human = HumanMessage(content="question")

        kept = [ai_msg, tool_msg, human]
        result, _preserved_count, _preserved_chars, compressed_count, compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, [])
        )

        assert result[1].content == short_content
        assert compressed_count == 0
        assert compressed_chars_saved == 0

    def test_no_human_message_skips_truncation(self):
        """When no HumanMessage in kept, last_human_idx is -1 so nothing is truncated."""
        long_content = "x" * (TRANSIENT_COMPRESS_MAX_CHARS + 100)
        ai_msg = self._create_ai_message_with_tools(["search"])
        tool_msg = self._tool_msg("call_search_0", long_content, RETENTION_TRANSIENT)

        kept = [ai_msg, tool_msg]
        result, _preserved_count, _preserved_chars, compressed_count, compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, [])
        )

        assert result[1].content == long_content
        assert compressed_count == 0
        assert compressed_chars_saved == 0

    def test_mixed_dropped_groups_preserves_only_long_lived(self):
        """Only long-lived outputs from dropped groups are preserved; transient are discarded."""
        ll_tool = self._tool_msg("call_load_spec_0", "spec data", RETENTION_LONG_LIVED)
        ai_ll = self._create_ai_message_with_tools(["load_spec"])
        tr_tool = self._tool_msg("call_search_0", "search data", RETENTION_TRANSIENT)
        ai_tr = self._create_ai_message_with_tools(["search"])
        dropped_groups = [[ai_ll, ll_tool], [ai_tr, tr_tool]]

        kept = [HumanMessage(content="hi")]
        result, preserved_count, _preserved_chars, _compressed_count, _compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, dropped_groups)
        )

        assert len(result) == 2
        preserved = result[0]
        assert isinstance(preserved, SystemMessage)
        assert "spec data" in preserved.content
        assert "search data" not in preserved.content
        assert preserved_count == 1

    def test_empty_dropped_groups_no_preserved_header(self):
        """No SystemMessage prefix when there are no dropped groups."""
        kept = [HumanMessage(content="hi"), AIMessage(content="hello")]
        result, preserved_count, _preserved_chars, _compressed_count, _compressed_chars_saved = (
            self.preparer._compress_and_preserve(kept, [])
        )

        assert len(result) == 2
        assert not any(isinstance(m, SystemMessage) for m in result)
        assert preserved_count == 0
