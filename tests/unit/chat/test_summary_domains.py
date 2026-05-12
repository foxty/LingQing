"""Unit tests for ThreadSummaryDomain and SessionSummaryDomain."""

from datetime import datetime, timedelta, timezone

from apps.tenant_app_service.chat.domain import (
    MessageDomain,
    SessionSummaryDomain,
    ThreadSummaryDomain,
)


def c_msg(
    role: str,
    content: str,
    message_id: str = "msg_test",
    session_id: str = "s1",
    timestamp: datetime | None = None,
    tool_calls: list[dict] | None = None,
) -> MessageDomain:
    """Helper to create MessageDomain with minimal args."""
    return MessageDomain(
        message_id=message_id,
        agent_id=1,
        thread_id="t1",
        session_id=session_id,
        role=role,
        content=content,
        timestamp=timestamp,
        tool_calls=tool_calls,
    )


class TestSessionSummaryDomainInit:
    """Test SessionSummaryDomain initialization and post_init extraction."""

    def test_init_with_human_and_ai_messages(self):
        """Test initialization with human and AI messages."""
        base_time = datetime.now(timezone.utc)
        messages = [
            c_msg("human", "What is 2+2?", timestamp=base_time),
            c_msg("ai", "2+2=4", message_id="msg2", timestamp=base_time + timedelta(seconds=1)),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.session_id == "s1"
        assert session.thread_id == "t1"
        assert len(session.messages) == 2
        assert session.user_intent == "What is 2+2?"
        assert session.tools_used == []
        assert session.key_results == "2+2=4"

    def test_init_with_empty_messages(self):
        """Test initialization with empty messages list."""
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=[])

        assert session.user_intent == "No user intent found"
        assert session.tools_used == []
        assert session.key_results == "No results found"
        assert session.message_time_range == {"from_time": None, "to_time": None, "count": 0}

    def test_init_with_long_user_intent(self):
        """Test that user intent is truncated to 500 chars."""
        long_content = "a" * 600
        messages = [c_msg("human", long_content), c_msg("ai", "OK", message_id="msg2")]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert len(session.user_intent) == 500
        assert session.user_intent == "a" * 500


class TestExtractUserIntent:
    """Test user intent extraction from messages."""

    def test_extract_from_first_human_message(self):
        """Test extracting user intent from first human message."""
        messages = [
            c_msg("human", "First user message"),
            c_msg("ai", "Response", message_id="msg2"),
            c_msg("human", "Second user message", message_id="msg3"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.user_intent == "First user message"

    def test_extract_with_whitespace(self):
        """Test that whitespace is stripped."""
        messages = [c_msg("human", "  Trimmed message  ")]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.user_intent == "Trimmed message"

    def test_no_human_message(self):
        """Test fallback when no human message exists."""
        messages = [c_msg("ai", "Just AI response")]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.user_intent == "No user intent found"


class TestExtractToolsUsed:
    """Test tool extraction from AI messages."""

    def test_extract_single_tool(self):
        """Test extracting a single tool."""
        messages = [
            c_msg("human", "Use tool A"),
            c_msg(
                "ai",
                "Using tool A",
                message_id="msg2",
                tool_calls=[{"name": "tool_a", "args": {}}],
            ),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.tools_used == ["tool_a"]

    def test_extract_multiple_tools(self):
        """Test extracting multiple tools (deduplicated and sorted)."""
        messages = [
            c_msg("human", "Use tools"),
            c_msg(
                "ai",
                "Using tools",
                message_id="msg2",
                tool_calls=[{"name": "tool_c", "args": {}}, {"name": "tool_a", "args": {}}],
            ),
            c_msg(
                "ai",
                "Using more tools",
                message_id="msg3",
                tool_calls=[{"name": "tool_b", "args": {}}, {"name": "tool_a", "args": {}}],
            ),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.tools_used == ["tool_a", "tool_b", "tool_c"]

    def test_no_tool_calls(self):
        """Test when no tool calls are made."""
        messages = [
            c_msg("human", "No tools"),
            c_msg("ai", "Response without tools", message_id="msg2"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.tools_used == []

    def test_malformed_tool_calls_ignored(self):
        """Test that malformed tool calls without 'name' are ignored."""
        messages = [
            c_msg("human", "Use tool"),
            c_msg(
                "ai",
                "Using tool",
                message_id="msg2",
                tool_calls=[{"args": {}}, {"name": "tool_a", "args": {}}],  # Missing name in first
            ),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.tools_used == ["tool_a"]


class TestExtractKeyResults:
    """Test key results extraction."""

    def test_extract_from_last_ai_message_without_tools(self):
        """Test extracting from last AI message without tool calls."""
        messages = [
            c_msg("human", "Query"),
            c_msg("ai", "Searching...", message_id="msg2", tool_calls=[{"name": "search"}]),
            c_msg("ai", "Final answer: 42", message_id="msg3"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.key_results == "Final answer: 42"

    def test_extract_with_whitespace_stripped(self):
        """Test that whitespace is stripped from results."""
        messages = [
            c_msg("human", "Query"),
            c_msg("ai", "  Result with padding  ", message_id="msg2"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.key_results == "Result with padding"

    def test_fallback_when_all_ai_have_tools(self):
        """Test fallback when all AI messages have tool calls."""
        messages = [
            c_msg("human", "Query"),
            c_msg(
                "ai",
                "Searching...",
                message_id="msg2",
                tool_calls=[{"name": "search"}],
            ),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.key_results == "No results found"

    def test_no_ai_message(self):
        """Test fallback when no AI message exists."""
        messages = [c_msg("human", "Question")]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.key_results == "No results found"


class TestComputeMessageTimeRange:
    """Test message time range computation."""

    def test_with_timestamps(self):
        """Test time range with valid timestamps."""
        base_time = datetime.now(timezone.utc)
        messages = [
            c_msg("human", "Q1", timestamp=base_time),
            c_msg("ai", "A1", message_id="msg2", timestamp=base_time + timedelta(seconds=5)),
            c_msg("human", "Q2", message_id="msg3", timestamp=base_time + timedelta(seconds=10)),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.message_time_range["count"] == 3
        assert session.message_time_range["from_time"] == base_time.isoformat()
        assert session.message_time_range["to_time"] == (base_time + timedelta(seconds=10)).isoformat()

    def test_without_timestamps(self):
        """Test time range when messages have no timestamps."""
        messages = [c_msg("human", "Q1"), c_msg("ai", "A1", message_id="msg2")]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.message_time_range["from_time"] is None
        assert session.message_time_range["to_time"] is None
        assert session.message_time_range["count"] == 2

    def test_with_empty_messages(self):
        """Test time range with empty message list."""
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=[])

        assert session.message_time_range == {"from_time": None, "to_time": None, "count": 0}


class TestReadyForLlmSummary:
    """Test LLM readiness criteria."""

    def test_big_results(self):
        """Test that big results (>=1000 chars) makes session ready."""
        messages = [
            c_msg("human", "Analyze data"),
            c_msg("ai", "a" * 1000, message_id="msg2"),  # 1000 chars
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.ready_for_llm_summary() is True

    def test_enough_messages_with_tools(self):
        """Test readiness with >=3 messages and tool usage."""
        messages = [
            c_msg("human", "Q1"),
            c_msg("ai", "Using tool", message_id="msg2", tool_calls=[{"name": "search"}]),
            c_msg("human", "Q2", message_id="msg3"),
            c_msg("ai", "Result", message_id="msg4"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.ready_for_llm_summary() is True

    def test_not_ready_few_messages_no_tools(self):
        """Test not ready with <3 messages and no tools."""
        messages = [
            c_msg("human", "Q1"),
            c_msg("ai", "A1", message_id="msg2"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.ready_for_llm_summary() is False

    def test_not_ready_no_tools_small_results(self):
        """Test not ready with >=3 messages but no tools and small results."""
        messages = [
            c_msg("human", "Q1"),
            c_msg("ai", "A1", message_id="msg2"),
            c_msg("human", "Q2", message_id="msg3"),
            c_msg("ai", "short", message_id="msg4"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        assert session.ready_for_llm_summary() is False


class TestGenSummaryText:
    """Test summary text generation."""

    def test_gen_summary_with_all_fields(self):
        """Test generating summary with all fields populated."""
        messages = [
            c_msg("human", "Analyze sales data"),
            c_msg(
                "ai",
                "Running analysis",
                message_id="msg2",
                tool_calls=[{"name": "db_query"}, {"name": "chart_gen"}],
            ),
            c_msg("ai", "Sales up 20%", message_id="msg3"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)
        summary = session.gen_summary_text()

        assert "Session (s1) Summary" in summary
        assert "User Intent: Analyze sales data" in summary
        assert "Tools Used: chart_gen, db_query" in summary
        assert "Key Results: Sales up 20%" in summary

    def test_gen_summary_with_no_tools(self):
        """Test summary when no tools were used."""
        messages = [
            c_msg("human", "Simple question"),
            c_msg("ai", "Simple answer", message_id="msg2"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)
        summary = session.gen_summary_text()

        assert "Tools Used: None" in summary


class TestSessionSummaryFromMessages:
    """Test SessionSummaryDomain.from_messages factory."""

    def test_from_messages_creates_domain(self):
        """Test creating SessionSummaryDomain from messages."""
        messages = [
            c_msg("human", "Q1"),
            c_msg("ai", "A1", message_id="msg2"),
        ]
        session = SessionSummaryDomain.from_messages("s1", "t1", messages)

        assert session.session_id == "s1"
        assert session.thread_id == "t1"
        assert len(session.messages) == 2
        assert session.user_intent == "Q1"


class TestThreadSummaryDomainCreateFromSessions:
    """Test ThreadSummaryDomain.create_from_sessions factory."""

    def test_create_from_single_session(self):
        """Test creating thread summary from a single session."""
        # Create a session
        messages = [
            c_msg("human", "Question"),
            c_msg("ai", "Answer", message_id="msg2"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        # Create thread summary
        thread_summary = ThreadSummaryDomain.create_from_sessions(
            thread_id="t1",
            tenant_id=1,
            version=1,
            sessions=[session],
            summary_content="# Summary\n\nQuestion was answered.",
        )

        assert thread_summary.thread_id == "t1"
        assert thread_summary.tenant_id == 1
        assert thread_summary.version == 1
        assert thread_summary.session_count == 1
        assert "# Summary" in thread_summary.summary_content
        assert thread_summary.session_range["from_session_id"] == "s1"
        assert thread_summary.session_range["to_session_id"] == "s1"
        assert thread_summary.session_range["session_count"] == 1

    def test_create_from_multiple_sessions(self):
        """Test creating thread summary from multiple sessions."""
        base_time = datetime.now(timezone.utc)

        # Session 1
        messages1 = [
            c_msg("human", "Q1", session_id="s1", timestamp=base_time),
            c_msg(
                "ai",
                "A1",
                message_id="msg2",
                session_id="s1",
                timestamp=base_time + timedelta(seconds=1),
            ),
        ]
        session1 = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages1)

        # Session 2
        messages2 = [
            c_msg("human", "Q2", session_id="s2", timestamp=base_time + timedelta(seconds=5)),
            c_msg(
                "ai",
                "A2",
                message_id="msg3",
                session_id="s2",
                timestamp=base_time + timedelta(seconds=6),
            ),
        ]
        session2 = SessionSummaryDomain(session_id="s2", thread_id="t1", messages=messages2)

        # Create thread summary
        thread_summary = ThreadSummaryDomain.create_from_sessions(
            thread_id="t1",
            tenant_id=1,
            version=1,
            sessions=[session1, session2],
            summary_content="# Summary\n\nBoth questions answered.",
        )

        assert thread_summary.session_count == 2
        assert thread_summary.session_range["from_session_id"] == "s1"
        assert thread_summary.session_range["to_session_id"] == "s2"
        assert thread_summary.session_range["session_count"] == 2

    def test_message_time_range_aggregation(self):
        """Test that message time range aggregates across sessions."""
        base_time = datetime.now(timezone.utc)

        # Session 1: early times
        messages1 = [
            c_msg("human", "Q1", session_id="s1", timestamp=base_time),
            c_msg(
                "ai",
                "A1",
                message_id="msg2",
                session_id="s1",
                timestamp=base_time + timedelta(seconds=5),
            ),
        ]
        session1 = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages1)

        # Session 2: later times
        messages2 = [
            c_msg("human", "Q2", session_id="s2", timestamp=base_time + timedelta(minutes=5)),
            c_msg(
                "ai",
                "A2",
                message_id="msg3",
                session_id="s2",
                timestamp=base_time + timedelta(minutes=5, seconds=5),
            ),
        ]
        session2 = SessionSummaryDomain(session_id="s2", thread_id="t1", messages=messages2)

        thread_summary = ThreadSummaryDomain.create_from_sessions(
            thread_id="t1",
            tenant_id=1,
            version=1,
            sessions=[session1, session2],
            summary_content="# Summary",
        )

        assert thread_summary.message_range["from_time"] == base_time.isoformat()
        assert thread_summary.message_range["to_time"] == (base_time + timedelta(minutes=5, seconds=5)).isoformat()
        assert thread_summary.message_range["count"] == 4  # 4 messages total


class TestThreadSummaryDomainMetrics:
    """Test token savings and compression metrics."""

    def test_get_token_savings(self):
        """Test token savings calculation."""
        messages = [
            c_msg("human", "Q1", session_id="s1"),
            c_msg("ai", "A1", message_id="msg2", session_id="s1"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)

        # Create with specific token counts
        thread_summary = ThreadSummaryDomain(
            thread_id="t1",
            tenant_id=1,
            version=1,
            summary_content="Summary",
            session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
            message_range={"from_time": None, "to_time": None, "count": 2},
            session_count=1,
            token_count_before=1000,
            token_count_after=200,
        )

        assert thread_summary.get_token_savings() == 800

    def test_get_compression_ratio(self):
        """Test compression ratio calculation."""
        thread_summary = ThreadSummaryDomain(
            thread_id="t1",
            tenant_id=1,
            version=1,
            summary_content="Summary",
            session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
            message_range={"from_time": None, "to_time": None, "count": 1},
            session_count=1,
            token_count_before=1000,
            token_count_after=400,
        )

        assert thread_summary.get_compression_ratio() == 0.4

    def test_get_compression_ratio_zero_before(self):
        """Test compression ratio when before count is zero."""
        thread_summary = ThreadSummaryDomain(
            thread_id="t1",
            tenant_id=1,
            version=1,
            summary_content="Summary",
            session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
            message_range={"from_time": None, "to_time": None, "count": 1},
            session_count=1,
            token_count_before=0,
            token_count_after=100,
        )

        assert thread_summary.get_compression_ratio() == 0.0

    def test_format_token_metrics_compression(self):
        thread_summary = ThreadSummaryDomain(
            thread_id="t1",
            tenant_id=1,
            version=1,
            summary_content="Summary",
            session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
            message_range={"from_time": None, "to_time": None, "count": 1},
            session_count=1,
            token_count_before=1000,
            token_count_after=400,
        )

        assert thread_summary.format_token_metrics() == "saved 600 tokens (40.0% of input)"

    def test_format_token_metrics_expansion(self):
        thread_summary = ThreadSummaryDomain(
            thread_id="t1",
            tenant_id=1,
            version=1,
            summary_content="Summary",
            session_range={"from_session_id": "s1", "to_session_id": "s1", "session_count": 1},
            message_range={"from_time": None, "to_time": None, "count": 1},
            session_count=1,
            token_count_before=513,
            token_count_after=1313,
        )

        assert thread_summary.format_token_metrics() == "expanded by 800 tokens (255.9% of input)"

    def test_token_count_before_uses_session_summary_text(self):
        messages = [
            c_msg("human", "Question"),
            c_msg("ai", "Answer", message_id="msg2"),
        ]
        session = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages)
        session.summary = "Detailed session summary with much more context than intent and results alone."

        thread_summary = ThreadSummaryDomain.create_from_sessions(
            thread_id="t1",
            tenant_id=1,
            version=1,
            sessions=[session],
            summary_content="Compact thread summary.",
        )

        from langchain_core.messages import SystemMessage

        from apps.tenant_app_service.agents.token_counter import count_tokens

        expected_before = count_tokens([SystemMessage(content=session.summary)])
        assert thread_summary.token_count_before == expected_before


class TestThreadSummaryDomainFallback:
    """Test ThreadSummaryDomain.create_with_fallback_summary."""

    def test_create_with_fallback_generates_summary(self):
        """Test that fallback creates a valid summary."""
        messages1 = [
            c_msg("human", "First question", session_id="s1"),
            c_msg("ai", "First answer", message_id="msg2", session_id="s1"),
        ]
        session1 = SessionSummaryDomain(session_id="s1", thread_id="t1", messages=messages1)

        messages2 = [
            c_msg("human", "Second question", session_id="s2"),
            c_msg("ai", "Second answer", message_id="msg3", session_id="s2"),
        ]
        session2 = SessionSummaryDomain(session_id="s2", thread_id="t1", messages=messages2)

        thread_summary = ThreadSummaryDomain.create_with_fallback_summary(
            thread_id="t1",
            tenant_id=1,
            version=1,
            sessions=[session1, session2],
        )

        assert thread_summary.thread_id == "t1"
        assert thread_summary.session_count == 2
        assert "# Thread Summary (no llm available)" in thread_summary.summary_content
        assert "Covered 2 sessions" in thread_summary.summary_content
        assert "s1" in thread_summary.summary_content
        assert "s2" in thread_summary.summary_content
