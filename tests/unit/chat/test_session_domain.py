"""Unit tests for SessionSummaryDomain."""

from datetime import datetime, timedelta

from apps.tenant_app_service.chat.domain import MessageDomain, SessionSummaryDomain


def c_msg(role: str, content: str, timestamp: datetime = None, tool_calls: list[dict] | None = None) -> MessageDomain:
    """Helper to create MessageDomain with minimal args."""
    return MessageDomain(
        message_id="msg_test",
        agent_id=1,
        thread_id="t1",
        session_id="s1",
        role=role,
        content=content,
        timestamp=timestamp,
        tool_calls=tool_calls,
    )


class TestSessionSummaryDomainInit:
    """Test SessionSummaryDomain initialization."""

    def test_init_with_valid_messages(self):
        """Test initialization with valid messages."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Hello",
                timestamp=datetime.utcnow(),
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Hi there",
                timestamp=datetime.utcnow(),
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.session_id == "session_123"
        assert session.thread_id == "thread_456"
        assert len(session.messages) == 2

    def test_init_with_empty_messages(self):
        """Test initialization with empty messages list."""
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=[],
        )

        assert session.session_id == "session_123"
        assert session.thread_id == "thread_456"
        assert session.messages == []
        assert session.user_intent == "No user intent found"
        assert session.tools_used == []
        assert session.key_results == "No results found"


class TestExtractUserIntent:
    """Test user intent extraction."""

    def test_extract_user_intent_from_first_human_message(self):
        """Test extracting user intent from first human message."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="What is the weather?",
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="It's sunny",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.user_intent == "What is the weather?"

    def test_extract_user_intent_truncated(self):
        """Test user intent is truncated to 500 chars."""
        long_content = "x" * 600
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content=long_content,
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert len(session.user_intent) == 500
        assert session.user_intent == "x" * 500

    def test_extract_user_intent_no_human_message(self):
        """Test when no human message exists."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Hello",
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="tool",
                content="Result",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.user_intent == "No user intent found"

    def test_extract_user_intent_ignores_whitespace(self):
        """Test that user intent strips leading/trailing whitespace."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="   What is the meaning of life?   ",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.user_intent == "What is the meaning of life?"


class TestExtractToolsUsed:
    """Test tools used extraction."""

    def test_extract_tools_used_single_tool(self):
        """Test extracting single tool used."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Search for something",
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Searching",
                tool_calls=[{"name": "search"}],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.tools_used == ["search"]

    def test_extract_tools_used_multiple_tools(self):
        """Test extracting multiple unique tools."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Using tools",
                tool_calls=[{"name": "search"}, {"name": "calculator"}],
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Using more tools",
                tool_calls=[{"name": "search"}, {"name": "database"}],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.tools_used == ["calculator", "database", "search"]

    def test_extract_tools_used_no_tools(self):
        """Test when no tools are used."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Hi",
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Hello",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.tools_used == []

    def test_extract_tools_used_ignores_non_ai_messages(self):
        """Test that tool calls in non-AI messages are ignored."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="tool",
                content="Tool result",
                tool_calls=[{"name": "should_be_ignored"}],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.tools_used == []

    def test_extract_tools_used_handles_invalid_tool_calls(self):
        """Test that invalid tool call formats are handled gracefully."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Mixed tools",
                tool_calls=[
                    {"name": "valid_tool"},
                    {"no_name": "invalid"},
                    "not_a_dict",
                ],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.tools_used == ["valid_tool"]

    def test_extract_tools_used_sorted(self):
        """Test that tools are returned in sorted order."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Tools",
                tool_calls=[
                    {"name": "zebra"},
                    {"name": "apple"},
                    {"name": "monkey"},
                ],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.tools_used == ["apple", "monkey", "zebra"]


class TestExtractKeyResults:
    """Test key results extraction."""

    def test_extract_key_results_from_last_ai_message_without_tools(self):
        """Test extracting results from last AI message without tool calls."""
        messages = [
            MessageDomain(
                message_id="msg0",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Search for cats",
            ),
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Searching",
                tool_calls=[{"name": "search"}],
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="tool",
                content="Found 5 articles",
            ),
            MessageDomain(
                message_id="msg3",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Here are the results about cats",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.key_results == "Here are the results about cats"

    def test_extract_key_results_no_ai_message(self):
        """Test when no AI message exists."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Hello",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.key_results == "No results found"

    def test_extract_key_results_all_ai_messages_have_tools(self):
        """Test when all AI messages have tool calls."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Tool 1",
                tool_calls=[{"name": "search"}],
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Tool 2",
                tool_calls=[{"name": "db"}],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.key_results == "No results found"

    def test_extract_key_results_strips_whitespace(self):
        """Test that key results are stripped of whitespace."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="   Final answer with spaces   ",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        assert session.key_results == "Final answer with spaces"


class TestMessageTimeRange:
    """Test message time range calculation."""

    def test_message_time_range_with_timestamps(self):
        """Test time range with valid timestamps."""
        now = datetime.utcnow()
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Hi",
                timestamp=now,
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Hello",
                timestamp=now + timedelta(seconds=5),
            ),
            MessageDomain(
                message_id="msg3",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Result",
                timestamp=now + timedelta(seconds=10),
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        time_range = session.message_time_range
        assert time_range["from_time"] == now.isoformat()
        assert time_range["to_time"] == (now + timedelta(seconds=10)).isoformat()
        assert time_range["count"] == 3

    def test_message_time_range_without_timestamps(self):
        """Test time range when messages have no timestamps."""
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Hi",
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Hello",
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        time_range = session.message_time_range
        assert time_range["from_time"] is None
        assert time_range["to_time"] is None
        assert time_range["count"] == 2

    def test_message_time_range_mixed_timestamps(self):
        """Test time range with some messages having timestamps."""
        now = datetime.utcnow()
        messages = [
            MessageDomain(
                message_id="msg1",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="human",
                content="Hi",
                timestamp=now,
            ),
            MessageDomain(
                message_id="msg2",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Hello",
            ),  # No timestamp
            MessageDomain(
                message_id="msg3",
                agent_id=1,
                thread_id="thread_456",
                session_id="session_123",
                role="ai",
                content="Result",
                timestamp=now + timedelta(seconds=5),
            ),
        ]
        session = SessionSummaryDomain(
            session_id="session_123",
            thread_id="thread_456",
            messages=messages,
        )

        time_range = session.message_time_range
        assert time_range["from_time"] == now.isoformat()
        assert time_range["to_time"] == (now + timedelta(seconds=5)).isoformat()
        assert time_range["count"] == 3

    def test_message_time_range_empty_messages(self):
        """Test time range with no messages."""
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=[],
        )

        time_range = session.message_time_range
        assert time_range["from_time"] is None
        assert time_range["to_time"] is None
        assert time_range["count"] == 0


class TestReadyForLlmSummary:
    """Test LLM summary readiness logic."""

    def test_ready_when_big_results(self):
        """Test ready for summary when key results are large (>= 1000 chars)."""
        messages = [
            c_msg(role="human", content="Q"),
            c_msg(role="ai", content="x" * 1000),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is True

    def test_ready_when_enough_messages_and_tools(self):
        """Test ready when has 3+ messages AND used tools."""
        messages = [
            c_msg(role="human", content="Search"),
            c_msg(
                role="ai",
                content="Searching",
                tool_calls=[{"name": "search"}],
            ),
            c_msg(role="tool", content="Results"),
            c_msg(role="ai", content="Done"),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is True

    def test_not_ready_few_messages_no_tools(self):
        """Test not ready with few messages and no tools."""
        messages = [
            c_msg(role="human", content="Hi"),
            c_msg(role="ai", content="Hello"),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is False

    def test_not_ready_many_messages_no_tools(self):
        """Test not ready with many messages but no tools."""
        messages = [
            c_msg(role="human", content="Q1"),
            c_msg(role="ai", content="A1"),
            c_msg(role="human", content="Q2"),
            c_msg(role="ai", content="A2"),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is False

    def test_not_ready_few_messages_with_tools(self):
        """Test not ready with few messages even if tools used."""
        messages = [
            c_msg(
                role="ai",
                content="Tool",
                tool_calls=[{"name": "search"}],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is False

    def test_ready_exactly_1000_chars(self):
        """Test ready when results are exactly 1000 chars."""
        messages = [
            c_msg(role="human", content="Q"),
            c_msg(role="ai", content="x" * 1000),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is True

    def test_not_ready_999_chars_no_other_criteria(self):
        """Test not ready with 999 char results and no other criteria."""
        messages = [
            c_msg(role="human", content="Q"),
            c_msg(role="ai", content="x" * 999),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        assert session.ready_for_llm_summary() is False


class TestGenSummaryText:
    """Test summary text generation."""

    def test_gen_summary_text_complete(self):
        """Test generating summary with all information."""
        now = datetime.utcnow()
        messages = [
            c_msg(role="human", content="Find weather info", timestamp=now),
            c_msg(
                role="ai",
                content="Getting weather",
                tool_calls=[{"name": "weather_api"}],
                timestamp=now + timedelta(seconds=1),
            ),
            c_msg(
                role="ai",
                content="Weather is sunny and 72F",
                timestamp=now + timedelta(seconds=2),
            ),
        ]
        session = SessionSummaryDomain(
            session_id="s123",
            thread_id="t456",
            messages=messages,
        )

        summary = session.gen_summary_text()
        assert "s123" in summary
        assert "Find weather info" in summary
        assert "weather_api" in summary
        assert "Weather is sunny and 72F" in summary

    def test_gen_summary_text_no_tools(self):
        """Test summary with no tools used."""
        messages = [
            c_msg(role="human", content="Hi"),
            c_msg(role="ai", content="Hello"),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )

        summary = session.gen_summary_text()
        assert "None" in summary
        assert "Hi" in summary

    def test_gen_summary_text_format(self):
        """Test that summary text has expected format."""
        messages = [
            c_msg(role="human", content="Query"),
            c_msg(role="ai", content="Response"),
        ]
        session = SessionSummaryDomain(
            session_id="sess_1",
            thread_id="thread_1",
            messages=messages,
        )

        summary = session.gen_summary_text()
        assert "Session" in summary
        assert "User Intent:" in summary
        assert "Tools Used:" in summary
        assert "Key Results:" in summary


class TestFromMessages:
    """Test creating SessionSummaryDomain from domain messages."""

    def test_from_messages_complete(self):
        """Test creating session from complete domain messages."""
        now = datetime.utcnow()
        msg1 = c_msg("human", "Hello", timestamp=now)
        msg2 = c_msg("ai", "Hi there", timestamp=now + timedelta(seconds=1), tool_calls=[{"name": "search"}])

        session = SessionSummaryDomain.from_messages(
            session_id="s1",
            thread_id="t1",
            messages=[msg1, msg2],
        )

        assert session.session_id == "s1"
        assert session.thread_id == "t1"
        assert len(session.messages) == 2
        assert session.messages[0].role == "human"
        assert session.messages[1].role == "ai"

    def test_from_messages_with_tool_call_id(self):
        """Test creating session from messages with tool_call_id."""
        msg = MessageDomain(
            message_id="msg_1",
            thread_id="t1",
            role="tool",
            content="Tool result",
            timestamp=datetime.utcnow(),
            tool_calls=None,
            tool_call_id="tc_123",
            session_id="s1",
            agent_id=1,
        )

        session = SessionSummaryDomain.from_messages(
            session_id="s1",
            thread_id="t1",
            messages=[msg],
        )

        assert session.messages[0].tool_call_id == "tc_123"

    def test_from_messages_empty(self):
        """Test creating session from empty message list."""
        session = SessionSummaryDomain.from_messages(
            session_id="s1",
            thread_id="t1",
            messages=[],
        )

        assert session.session_id == "s1"
        assert session.thread_id == "t1"
        assert len(session.messages) == 0

    def test_from_messages_preserves_metadata(self):
        """Test that metadata is preserved from domain messages."""
        msg = MessageDomain(
            message_id="msg_1",
            thread_id="t1",
            role="human",
            content="Question",
            timestamp=datetime.utcnow(),
            tool_calls=None,
            session_id="s1",
            agent_id=1,
            message_metadata={"session_id": "sess_1", "extra": "data"},
            additional_kwargs={"key": "value"},
        )

        session = SessionSummaryDomain.from_messages(
            session_id="s1",
            thread_id="t1",
            messages=[msg],
        )

        m = session.messages[0]
        assert m.message_metadata == {"session_id": "sess_1", "extra": "data"}
        assert m.additional_kwargs == {"key": "value"}


class TestProperties:
    """Test SessionSummaryDomain properties."""

    def test_session_id_property(self):
        """Test session_id property getter."""
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=[],
        )
        assert session.session_id == "s1"

    def test_thread_id_property(self):
        """Test thread_id property getter."""
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=[],
        )
        assert session.thread_id == "t1"

    def test_user_intent_property(self):
        """Test user_intent property getter."""
        messages = [c_msg(role="human", content="Test intent")]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )
        assert session.user_intent == "Test intent"

    def test_tools_used_property(self):
        """Test tools_used property getter."""
        messages = [
            c_msg(
                role="ai",
                content="Tool usage",
                tool_calls=[{"name": "tool1"}],
            ),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )
        assert session.tools_used == ["tool1"]

    def test_key_results_property(self):
        """Test key_results property getter."""
        messages = [
            c_msg(role="ai", content="Final result"),
        ]
        session = SessionSummaryDomain(
            session_id="s1",
            thread_id="t1",
            messages=messages,
        )
        assert session.key_results == "Final result"


class TestToolChainResolution:
    def test_extract_tool_call_ids(self):
        from apps.tenant_app_service.chat.domain import extract_tool_call_ids

        assert extract_tool_call_ids(None) == []
        assert extract_tool_call_ids([{"id": "tc1", "name": "t"}]) == ["tc1"]
        assert extract_tool_call_ids([{"name": "t"}, {"id": "tc2"}]) == ["tc2"]

    def test_is_tool_chain_resolved(self):
        from apps.tenant_app_service.chat.domain import is_tool_chain_resolved

        assert is_tool_chain_resolved([], set(), True) is False
        assert is_tool_chain_resolved(["tc1"], set(), True) is False
        assert is_tool_chain_resolved(["tc1"], {"tc1"}, False) is False
        assert is_tool_chain_resolved(["tc1", "tc2"], {"tc1"}, True) is False
        assert is_tool_chain_resolved(["tc1"], {"tc1"}, True) is True
