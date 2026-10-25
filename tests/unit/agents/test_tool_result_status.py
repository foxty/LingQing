"""Tests for persisted tool result / skip metadata helpers."""

from langchain_core.messages import ToolMessage

from apps.tenant_app_service.agents.tools.tool_result import (
    SKIP_CODE_KEY,
    TOOL_ERROR_KEY,
    TOOL_RESULT_STATUS_KEY,
    ToolResult,
    ToolResultStatus,
    ToolSkipCode,
    build_persisted_tool_skip_kwargs,
    tool_kwargs_indicate_limit_exceeded,
)


def test_build_persisted_tool_skip_kwargs():
    kwargs = build_persisted_tool_skip_kwargs(ToolSkipCode.TOOL_LIMIT_SIBLING, timestamp="t")
    assert kwargs[TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert kwargs[SKIP_CODE_KEY] == ToolSkipCode.TOOL_LIMIT_SIBLING
    assert kwargs["timestamp"] == "t"


def test_tool_kwargs_indicate_limit_exceeded_new_shape():
    kwargs = build_persisted_tool_skip_kwargs(ToolSkipCode.TOOL_LIMIT_EXCEEDED)
    assert tool_kwargs_indicate_limit_exceeded(kwargs) is True


def test_tool_kwargs_indicate_limit_exceeded_legacy_tool_error():
    kwargs = {TOOL_ERROR_KEY: {"code": ToolSkipCode.TOOL_LIMIT_EXCEEDED, "message": "limit"}}
    assert tool_kwargs_indicate_limit_exceeded(kwargs) is True


def test_tool_kwargs_indicate_limit_exceeded_negative():
    assert tool_kwargs_indicate_limit_exceeded({}) is False
    assert tool_kwargs_indicate_limit_exceeded({"tool_result_status": "skipped", "skip_code": "HITL_DEFERRED"}) is False


def test_tool_result_skipped_factory():
    result = ToolResult.skipped("Skipped: test", code=ToolSkipCode.HITL_DEFERRED)
    assert result.status == ToolResultStatus.SKIPPED
    assert result.metadata[SKIP_CODE_KEY] == ToolSkipCode.HITL_DEFERRED
