"""HITL test tools for approval workflow verification."""

from datetime import UTC, datetime

from langchain_core.tools import tool

from apps.tenant_app_service.agents.tools.tool_result import ToolResult


@tool
async def hitl_test_echo(text: str = "hitl test") -> ToolResult:
    """Return deterministic echo payload for HITL approval workflow testing.

    Use this tool only for testing the approval card and approval-resume execution flow.
    It performs no side effects.
    """
    return ToolResult.success(f"HITL_TEST_ECHO\\ntext={text}\\nexecuted_at={datetime.now(UTC).isoformat()}")
