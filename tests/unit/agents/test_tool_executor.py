"""Tests for ToolExecutor - Tool execution for agents.

This test file verifies that:
1. Single tool execution works correctly
2. Tool limits are enforced
3. Tool unavailability is handled gracefully
4. Tool execution errors are caught and reported
5. Tool call counts are tracked correctly
6. Session-scoped tool result caching works correctly
"""

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.tool_executor import ToolExecutor, _build_cache_key, _invalidate_cache
from apps.tenant_app_service.agents.tools import ToolResult, ToolResultStatus


class TestToolExecutor:
    """Test ToolExecutor functionality."""

    def setup_method(self):
        """Setup for each test."""
        # Create a mock config manager
        self.agent_config = MagicMock(spec=AgentConfig)
        self.executor = ToolExecutor(self.agent_config, "test_agent")

    def _create_tool_call(self, name: str, args: dict | None = None) -> dict:
        """Helper to create a tool call dict.

        Args:
            name: Tool name
            args: Tool arguments

        Returns:
            Tool call dict
        """
        return {
            "id": f"call_{name}_{uuid4().hex[:8]}",
            "name": name,
            "args": args or {"input": "test"},
        }


@pytest.mark.asyncio
class TestExecuteSingleTool(TestToolExecutor):
    """Test single tool execution."""

    async def test_execute_tool_success(self, runnable_config):
        """Test successful tool execution."""
        tool_call = self._create_tool_call("search", {"query": "test"})
        config = runnable_config

        # Mock tool config and execution
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Search results")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute
        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify
        assert isinstance(tool_message, ToolMessage)
        assert tool_message.content == "Search results"
        assert tool_message.tool_call_id == tool_call["id"]
        assert updated_counts["search"] == 1

        # Verify tool was invoked
        mock_tool.ainvoke.assert_called_once_with({"query": "test"}, config=config)

    async def test_execute_tool_with_tool_result(self, runnable_config):
        """Test tool execution returning ToolResult."""
        tool_call = self._create_tool_call("analyze")
        config = runnable_config

        # Mock tool returning ToolResult
        tool_result = ToolResult(
            content="Analysis result",
            metadata={"confidence": 0.95, "processing_time": 1.23},
        )
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = tool_result

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute
        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify content and metadata merged
        assert tool_message.content == "Analysis result"
        assert tool_message.additional_kwargs["confidence"] == 0.95
        assert tool_message.additional_kwargs["processing_time"] == 1.23

    async def test_execute_tool_not_available(self, runnable_config):
        """Test tool execution when tool is not available."""
        tool_call = self._create_tool_call("unavailable_tool")
        config = runnable_config

        # Tool config returns None (tool not available)
        self.agent_config.get_tool_config.return_value = None

        # Execute
        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify error message
        assert "tool call failed" in tool_message.content.lower()
        assert "not available" in tool_message.content.lower()
        assert tool_message.tool_call_id == tool_call["id"]
        assert tool_message.additional_kwargs["tool_error"]["code"] == "TOOL_NOT_AVAILABLE"
        assert updated_counts["unavailable_tool"] == 1

    async def test_execute_tool_limit_exceeded(self, runnable_config):
        """Test tool execution when limit is exceeded."""
        tool_call = self._create_tool_call("search")
        config = runnable_config

        # Tool config with limit of 3
        mock_tool_config = MagicMock()
        mock_tool_config.tool = MagicMock()
        mock_tool_config.limit = 3

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Already called 3 times
        existing_counts = {"search": 3}

        # Execute
        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, existing_counts, config)

        # Verify limit exceeded message
        assert "limit" in tool_message.content.lower()
        assert "3" in tool_message.content
        assert "Skipping this call" in tool_message.content
        mock_tool_config.tool.ainvoke.assert_not_called()
        # Counts should not change
        assert updated_counts == existing_counts

    async def test_execute_tool_limit_applies_at_boundary(self, runnable_config):
        """Calls up to limit should run; the next call must be skipped."""
        tool_call = self._create_tool_call("search", {"query": "test"})
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Results")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 2
        self.agent_config.get_tool_config.return_value = mock_tool_config

        counts: dict[str, int] = {}

        # 1st call: allowed
        msg_1, counts, _ = await self.executor.execute_single_tool(tool_call, counts, config)
        assert msg_1.content == "Results"
        assert counts["search"] == 1

        # 2nd call: still allowed (at limit after this call)
        msg_2, counts, _ = await self.executor.execute_single_tool(tool_call, counts, config)
        assert msg_2.content == "Results"
        assert counts["search"] == 2

        # 3rd call: blocked by limit
        msg_3, counts_after_block, _ = await self.executor.execute_single_tool(tool_call, counts, config)
        assert "limit: 2" in msg_3.content
        assert "Skipping this call" in msg_3.content
        assert counts_after_block == counts
        assert mock_tool.ainvoke.call_count == 2

    async def test_execute_tool_error_handling(self, runnable_config):
        """Test tool execution with error."""
        tool_call = self._create_tool_call("failing_tool")
        config = runnable_config

        # Mock tool that raises exception
        mock_tool = AsyncMock()
        mock_tool.ainvoke.side_effect = RuntimeError("Tool execution failed")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute
        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify error message
        assert "Tool call failed" in tool_message.content
        assert "Tool execution failed" in tool_message.content
        assert tool_message.additional_kwargs["tool_error"]["code"] == "TOOL_EXECUTION_EXCEPTION"
        # Failed calls should still count toward limit
        assert updated_counts["failing_tool"] == 1

    async def test_execute_tool_exception_rolls_back_runtime_session(self, runnable_config):
        """Exception in tool execution should rollback runtime db session."""
        tool_call = self._create_tool_call("failing_tool")
        mock_db_session = AsyncMock()
        config = RunnableConfig(configurable={**runnable_config["configurable"], "db_session": mock_db_session})

        mock_tool = AsyncMock()
        mock_tool.ainvoke.side_effect = RuntimeError("Tool execution failed")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10
        self.agent_config.get_tool_config.return_value = mock_tool_config

        await self.executor.execute_single_tool(tool_call, {}, config)

        mock_db_session.rollback.assert_awaited_once()

    async def test_execute_tool_business_error_from_tool_result(self, runnable_config):
        """ToolResult with error status should be treated as failed tool call."""
        tool_call = self._create_tool_call("biz_error_tool")
        mock_db_session = AsyncMock()
        config = RunnableConfig(configurable={**runnable_config["configurable"], "db_session": mock_db_session})

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult(
            content="Asset not authorized",
            status=ToolResultStatus.ERROR,
            metadata={"raw_result": {"error": "Asset not authorized"}},
        )

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10
        self.agent_config.get_tool_config.return_value = mock_tool_config

        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        assert "Tool call failed" in tool_message.content
        assert "Asset not authorized" in tool_message.content
        assert updated_counts["biz_error_tool"] == 1
        mock_db_session.rollback.assert_awaited_once()

    async def test_execute_tool_invalid_return_contract(self, runnable_config):
        """Non-ToolResult payload should fail contract validation."""
        tool_call = self._create_tool_call("legacy_error_tool")
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = '{"error": "Query blocked"}'

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10
        self.agent_config.get_tool_config.return_value = mock_tool_config

        tool_message, updated_counts, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        assert "Tool call failed" in tool_message.content
        assert "Invalid tool return contract" in tool_message.content
        assert updated_counts["legacy_error_tool"] == 1

    async def test_execute_tool_increments_count(self, runnable_config):
        """Test that tool call count is incremented."""
        tool_call = self._create_tool_call("search")
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Results")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # First call
        _, counts_1, _ = await self.executor.execute_single_tool(tool_call, {}, config)
        assert counts_1["search"] == 1

        # Second call with updated counts
        _, counts_2, _ = await self.executor.execute_single_tool(tool_call, counts_1, config)
        assert counts_2["search"] == 2

    async def test_execute_tool_with_empty_args(self, runnable_config):
        """Test tool execution with empty arguments."""
        # Create call with empty args dict
        tool_call = {
            "id": f"call_simple_tool_{uuid4().hex[:8]}",
            "name": "simple_tool",
            "args": {},
        }
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Simple result")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute
        tool_message, _, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify tool was called with empty args
        mock_tool.ainvoke.assert_called_once_with({}, config=config)
        assert tool_message.content == "Simple result"

    async def test_execute_tool_tracks_metadata(self, runnable_config):
        """Test that tool message includes proper metadata."""
        tool_call = self._create_tool_call("metadata_tool")
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Result")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute with specific loop count
        tool_message, _, _ = await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify metadata
        assert tool_message.additional_kwargs["tool_name"] == "metadata_tool"
        assert "timestamp" in tool_message.additional_kwargs


@pytest.mark.asyncio
class TestToolCountTracking(TestToolExecutor):
    """Test tool call count tracking."""

    async def test_multiple_tools_count_independently(self, runnable_config):
        """Test that different tools have independent counts."""
        search_call = self._create_tool_call("search")
        analyze_call = self._create_tool_call("analyze")
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Result")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute search twice
        _, counts_1, _ = await self.executor.execute_single_tool(search_call, {}, config)
        _, counts_2, _ = await self.executor.execute_single_tool(search_call, counts_1, config)

        # Execute analyze once
        _, counts_3, _ = await self.executor.execute_single_tool(analyze_call, counts_2, config)

        # Verify counts
        assert counts_3["search"] == 2
        assert counts_3["analyze"] == 1

    async def test_tool_count_preserved_on_error(self, runnable_config):
        """Test that failed calls are counted."""
        tool_call = self._create_tool_call("failing_tool")
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.side_effect = RuntimeError("Error")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        existing_counts = {"other_tool": 1}

        # Execute
        _, updated_counts, _ = await self.executor.execute_single_tool(tool_call, existing_counts, config)

        assert updated_counts["other_tool"] == 1
        assert updated_counts["failing_tool"] == 1


@pytest.mark.asyncio
class TestToolSkillInteraction(TestToolExecutor):
    """Test tool executor skill interactions."""

    async def test_get_tool_config_uses_loaded_skills(self, runnable_config):
        """Test that execute_single_tool uses loaded_skills for lookup."""
        tool_call = self._create_tool_call("skill_aware_tool")
        config = runnable_config

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("Skill result")

        mock_tool_config = MagicMock()
        mock_tool_config.tool = mock_tool
        mock_tool_config.limit = 10

        self.agent_config.get_tool_config.return_value = mock_tool_config

        # Execute with specific skill state
        await self.executor.execute_single_tool(tool_call, {}, config)

        # Verify get_tool_config was called with loaded skills
        self.agent_config.get_tool_config.assert_called_with([], "skill_aware_tool", ANY)

    async def test_different_skill_sets_use_different_configs(self, runnable_config):
        """Test that different loaded skill sets can have different tool configs."""
        tool_call = self._create_tool_call("flex_tool")
        config = runnable_config

        # Different tool configs for different skill sets
        default_config = MagicMock()
        default_mock_tool = AsyncMock()
        default_mock_tool.ainvoke.return_value = ToolResult.success("Default result")
        default_config.tool = default_mock_tool
        default_config.limit = 5

        admin_config = MagicMock()
        admin_mock_tool = AsyncMock()
        admin_mock_tool.ainvoke.return_value = ToolResult.success("Admin result")
        admin_config.tool = admin_mock_tool
        admin_config.limit = 20

        # Return different configs based on loaded skills
        def get_config_for_skills(skills, tool_name, runtime=None):
            if "admin" in skills:
                return admin_config
            return default_config

        self.agent_config.get_tool_config.side_effect = get_config_for_skills

        # Execute in base mode (no loaded skills)
        tool_msg_default, _, _ = await self.executor.execute_single_tool(tool_call, {}, config)
        assert tool_msg_default.content == "Default result"

        # Execute with admin skill loaded
        tool_msg_admin, _, _ = await self.executor.execute_single_tool(tool_call, {}, config, loaded_skills=["admin"])
        assert tool_msg_admin.content == "Admin result"


class TestCacheHelpers:
    """Test cache key building and invalidation helpers."""

    def test_build_cache_key_deterministic(self):
        key1 = _build_cache_key("read_file", {"path": "a.py", "offset": 1})
        key2 = _build_cache_key("read_file", {"offset": 1, "path": "a.py"})
        assert key1 == key2
        assert key1.startswith("read_file::")

    def test_build_cache_key_different_args(self):
        key1 = _build_cache_key("read_file", {"path": "a.py"})
        key2 = _build_cache_key("read_file", {"path": "b.py"})
        assert key1 != key2

    def test_invalidate_cache_removes_matching_entries(self):
        cache = {
            'read_file::{"path": "a.py"}': "content_a",
            'read_file::{"path": "b.py"}': "content_b",
            'list_files::{"dir": "/"}': "files",
        }
        result = _invalidate_cache(cache, ["read_file"])
        assert 'list_files::{"dir": "/"}' in result
        assert len(result) == 1

    def test_invalidate_cache_noop_when_empty_list(self):
        cache = {"read_file::{}": "content"}
        result = _invalidate_cache(cache, [])
        assert result is cache


@pytest.mark.asyncio
class TestToolCaching(TestToolExecutor):
    """Test session-scoped tool result caching in execute_single_tool."""

    def _make_cacheable_config(self, tool: AsyncMock, cache_invalidates: list[str] | None = None) -> MagicMock:
        cfg = MagicMock()
        cfg.tool = tool
        cfg.limit = 10
        cfg.cacheable = True
        cfg.cache_invalidates = cache_invalidates or []
        return cfg

    def _make_non_cacheable_config(self, tool: AsyncMock) -> MagicMock:
        cfg = MagicMock()
        cfg.tool = tool
        cfg.limit = 10
        cfg.cacheable = False
        cfg.cache_invalidates = []
        return cfg

    async def test_cacheable_tool_stores_result(self, runnable_config):
        """First call to a cacheable tool should store the result in cache."""
        tool_call = self._create_tool_call("read_file", {"path": "a.py"})
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("file content")

        self.agent_config.get_tool_config.return_value = self._make_cacheable_config(mock_tool)

        _, _, cache = await self.executor.execute_single_tool(tool_call, {}, runnable_config, tool_cache={})

        assert len(cache) == 1
        assert list(cache.values())[0] == "file content"

    async def test_cacheable_tool_returns_cached_on_second_call(self, runnable_config):
        """Second identical call should return cached result without invoking the tool."""
        args = {"path": "a.py"}
        call1 = self._create_tool_call("read_file", args)
        call2 = self._create_tool_call("read_file", args)

        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("file content")

        self.agent_config.get_tool_config.return_value = self._make_cacheable_config(mock_tool)

        msg1, counts, cache = await self.executor.execute_single_tool(call1, {}, runnable_config, tool_cache={})
        msg2, counts2, cache2 = await self.executor.execute_single_tool(
            call2, counts, runnable_config, tool_cache=cache
        )

        assert msg1.content == "file content"
        assert msg2.content == "file content"
        assert msg2.additional_kwargs.get("cached") is True
        mock_tool.ainvoke.assert_called_once()
        assert counts2["read_file"] == 2

    async def test_non_cacheable_tool_does_not_cache(self, runnable_config):
        """Non-cacheable tools should never store results."""
        tool_call = self._create_tool_call("search", {"q": "test"})
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult.success("results")

        self.agent_config.get_tool_config.return_value = self._make_non_cacheable_config(mock_tool)

        _, _, cache = await self.executor.execute_single_tool(tool_call, {}, runnable_config, tool_cache={})

        assert len(cache) == 0

    async def test_cache_invalidation_on_mutating_tool(self, runnable_config):
        """A mutating tool with cache_invalidates should clear matching entries."""
        read_args = {"path": "a.py"}
        read_call = self._create_tool_call("read_file", read_args)
        write_call = self._create_tool_call("write_file", {"path": "a.py", "content": "new"})

        read_tool = AsyncMock()
        read_tool.ainvoke.return_value = ToolResult.success("old content")
        write_tool = AsyncMock()
        write_tool.ainvoke.return_value = ToolResult.success("written")

        read_cfg = self._make_cacheable_config(read_tool)
        write_cfg = self._make_non_cacheable_config(write_tool)
        write_cfg.cache_invalidates = ["read_file"]

        def route_config(skills, name, runtime=None):
            return read_cfg if name == "read_file" else write_cfg

        self.agent_config.get_tool_config.side_effect = route_config

        # Populate cache
        _, counts, cache = await self.executor.execute_single_tool(read_call, {}, runnable_config, tool_cache={})
        assert len(cache) == 1

        # Write invalidates read_file entries
        _, counts, cache = await self.executor.execute_single_tool(
            write_call, counts, runnable_config, tool_cache=cache
        )
        assert len(cache) == 0

    async def test_error_result_not_cached(self, runnable_config):
        """Failed tool calls should not be stored in cache."""
        tool_call = self._create_tool_call("read_file", {"path": "missing.py"})
        mock_tool = AsyncMock()
        mock_tool.ainvoke.return_value = ToolResult(
            content="File not found",
            status=ToolResultStatus.ERROR,
        )

        self.agent_config.get_tool_config.return_value = self._make_cacheable_config(mock_tool)

        _, _, cache = await self.executor.execute_single_tool(tool_call, {}, runnable_config, tool_cache={})

        assert len(cache) == 0
