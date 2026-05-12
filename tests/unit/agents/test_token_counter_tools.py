"""Tests for tool definition token counting."""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.tenant_app_service.agents.token_counter import count_tokens, estimate_tool_chars


class SimpleToolArgs(BaseModel):
    """Simple tool arguments."""

    query: str = Field(description="The search query")


class ComplexToolArgs(BaseModel):
    """Complex tool arguments with multiple fields."""

    query: str = Field(description="SQL query to execute")
    datasource_id: int = Field(description="ID of the data source")
    limit: int = Field(default=100, description="Maximum number of rows to return")
    include_metadata: bool = Field(default=False, description="Whether to include metadata")


@tool
def simple_search_tool(query: str) -> str:
    """Search for information based on a query."""
    return f"Results for: {query}"


@tool(args_schema=SimpleToolArgs)
def search_with_schema(query: str) -> str:
    """Search tool with explicit schema."""
    return f"Results for: {query}"


@tool(args_schema=ComplexToolArgs)
def complex_sql_tool(query: str, datasource_id: int, limit: int = 100, include_metadata: bool = False) -> str:
    """Execute SQL query on a data source with various options."""
    return f"Query executed: {query}"


class TestEstimateToolTokens:
    """Tests for estimate_tool_tokens function."""

    def test_empty_tools_list(self):
        """Test with empty tools list."""
        char_count = estimate_tool_chars([])
        assert char_count == 0

    def test_single_simple_tool(self):
        """Test with single simple tool."""
        tools = [simple_search_tool]
        char_count = estimate_tool_chars(tools)
        # Should count: name + description + minimal schema (chars, not tokens)
        assert char_count > 40  # At least some characters

    def test_tool_with_explicit_schema(self):
        """Test tool with explicit Pydantic schema."""
        tools = [search_with_schema]
        char_count = estimate_tool_chars(tools)
        # Should count: name + description + schema (field descriptions)
        assert char_count > 60

    def test_complex_tool_with_multiple_parameters(self):
        """Test complex tool with multiple parameters and descriptions."""
        tools = [complex_sql_tool]
        char_count = estimate_tool_chars(tools)
        # Should count: name + description + full schema with 4 fields
        assert char_count > 120

    def test_multiple_tools(self):
        """Test character counting with multiple tools."""
        tools = [simple_search_tool, search_with_schema, complex_sql_tool]
        char_count = estimate_tool_chars(tools)
        # Should be sum of all tool definitions
        assert char_count > 200

    def test_tool_tokens_proportional_to_complexity(self):
        """Test that more complex tools use more characters."""
        simple_chars = estimate_tool_chars([simple_search_tool])
        complex_chars = estimate_tool_chars([complex_sql_tool])
        # Complex tool should use more characters
        assert complex_chars > simple_chars


class TestCountMessageTokensWithTools:
    """Tests for count_message_tokens with tools parameter."""

    def test_count_without_tools(self):
        """Test backward compatibility - counting without tools."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        token_count = count_tokens(messages)
        assert token_count == 3  # (5 + 8) / 4

    def test_count_with_empty_tools_list(self):
        """Test that empty tools list doesn't affect count."""
        messages = [HumanMessage(content="Test")]
        token_count = count_tokens(messages, tools=[])
        assert token_count == 1

    def test_count_with_single_tool(self):
        """Test counting with a single tool."""
        messages = [HumanMessage(content="Search for data")]
        tools = [simple_search_tool]

        token_count_without = count_tokens(messages)
        token_count_with = count_tokens(messages, tools=tools)

        # With tools should be higher
        assert token_count_with > token_count_without
        # Difference should be the tool tokens (chars / 4)
        tool_chars = estimate_tool_chars(tools)
        assert token_count_with == token_count_without + (tool_chars // 4)

    def test_count_with_multiple_tools(self):
        """Test counting with multiple tools."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="I can help with various tasks"),
        ]
        tools = [simple_search_tool, search_with_schema, complex_sql_tool]

        token_count = count_tokens(messages, tools=tools)
        tool_chars = estimate_tool_chars(tools)
        message_tokens = count_tokens(messages)

        # Should equal message tokens + tool tokens (chars / 4), allow for rounding
        expected = message_tokens + (tool_chars // 4)
        assert abs(token_count - expected) <= 1

    def test_count_with_system_prompt_and_tools(self):
        """Test counting with both system prompt and tools."""
        system_prompt = "You are a helpful assistant with access to tools."
        messages = [HumanMessage(content="Help me")]
        tools = [simple_search_tool, complex_sql_tool]

        # Count individual components
        message_tokens = count_tokens(messages)
        prompt_tokens = len(system_prompt) // 4
        tool_tokens = estimate_tool_chars(tools) // 4

        # Count combined
        total_tokens = count_tokens(messages, system_prompt=system_prompt, tools=tools)

        # Should equal sum of all components (allow 1 token difference for rounding)
        expected = message_tokens + prompt_tokens + tool_tokens
        assert abs(total_tokens - expected) <= 1

    def test_realistic_agent_scenario(self):
        """Test realistic scenario with agent conversation including tools."""
        system_prompt = """You are a data analysis agent.
You have access to SQL query tools and chart generation tools.
Always validate data before creating visualizations."""

        messages = [
            HumanMessage(content="分析最近三个月的销售趋势"),
            AIMessage(
                content="好的，我来查询销售数据",
                tool_calls=[{"id": "call1", "name": "sql_query", "args": {"query": "SELECT ..."}}],
            ),
        ]

        tools = [simple_search_tool, complex_sql_tool]

        # Without tools/prompt
        base_tokens = count_tokens(messages)

        # With tools only
        with_tools = count_tokens(messages, tools=tools)
        assert with_tools > base_tokens

        # With prompt only
        with_prompt = count_tokens(messages, system_prompt=system_prompt)
        assert with_prompt > base_tokens

        # With both
        with_all = count_tokens(messages, system_prompt=system_prompt, tools=tools)
        assert with_all > with_tools
        assert with_all > with_prompt

        # Should be highest because it includes everything (allow for rounding differences)
        expected = base_tokens + (len(system_prompt) // 4) + (estimate_tool_chars(tools) // 4)
        assert abs(with_all - expected) <= 1

    def test_large_tool_set_token_overhead(self):
        """Test that large tool sets contribute significant overhead."""
        messages = [HumanMessage(content="Hi")]
        base_tokens = count_tokens(messages)

        # Create multiple tools
        tools = [
            simple_search_tool,
            search_with_schema,
            complex_sql_tool,
        ] * 3  # 9 tools total

        with_tools = count_tokens(messages, tools=tools)
        overhead = with_tools - base_tokens

        # Large tool set should add significant overhead (100+ tokens)
        assert overhead > 100
