"""Unified tool result structure for agents.

This module provides a standardized return type for all tools, enabling:
- Separation of LLM content from system metadata
- Nested agent stats merging (agent-as-tool pattern)
- Flow control hints and execution status tracking
"""

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolResultStatus(StrEnum):
    """Tool execution status."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Partial success (e.g., data truncated)
    ERROR = "error"
    SKIPPED = "skipped"  # Not executed (limit, HITL batch deferral, policy)


# Persisted on tool message ``additional_kwargs`` for UI + history replay.
TOOL_RESULT_STATUS_KEY = "tool_result_status"
SKIP_CODE_KEY = "skip_code"
TOOL_ERROR_KEY = "tool_error"


class ToolErrorCode(StrEnum):
    """Stable ``tool_error.code`` values stamped by the executor (not skip/deferral)."""

    TOOL_NOT_AVAILABLE = "TOOL_NOT_AVAILABLE"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    TOOL_EXECUTION_EXCEPTION = "TOOL_EXECUTION_EXCEPTION"


class ToolSkipCode(StrEnum):
    """Reason a tool call was not executed (persisted under ``skip_code``)."""

    TOOL_LIMIT_EXCEEDED = "TOOL_LIMIT_EXCEEDED"
    TOOL_LIMIT_SIBLING = "TOOL_LIMIT_SIBLING"
    HITL_DEFERRED = "HITL_DEFERRED"
    TOOL_SKIPPED = "TOOL_SKIPPED"


def build_persisted_tool_skip_kwargs(skip_code: ToolSkipCode, **extra: Any) -> dict[str, Any]:
    """Build ``additional_kwargs`` for a synthetic skipped tool message."""
    return {
        TOOL_RESULT_STATUS_KEY: ToolResultStatus.SKIPPED,
        SKIP_CODE_KEY: skip_code,
        **extra,
    }


def tool_kwargs_indicate_limit_exceeded(kwargs: dict[str, Any] | None) -> bool:
    """True for limit-hit tool rows (current ``skipped`` shape or legacy ``tool_error``)."""
    data = kwargs or {}
    if (
        data.get(TOOL_RESULT_STATUS_KEY) == ToolResultStatus.SKIPPED
        and data.get(SKIP_CODE_KEY) == ToolSkipCode.TOOL_LIMIT_EXCEEDED
    ):
        return True
    tool_error = data.get(TOOL_ERROR_KEY)
    return isinstance(tool_error, dict) and tool_error.get("code") == ToolSkipCode.TOOL_LIMIT_EXCEEDED


@dataclass
class ToolError:
    """Structured error payload for tool failures.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable error message.
        retryable: Whether retry is recommended.
        hint: Optional operator/LLM hint for next action.
    """

    code: str
    message: str
    retryable: bool = False
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "hint": self.hint,
        }


@dataclass
class ToolResult:
    """Unified tool return structure.

    This structure separates:
    - content: What the LLM sees (for ToolMessage)
    - metadata: Comprehensive tool-level information including:
        - raw_result: Original tool return data (for debugging/analysis)
        - custom fields: Tool-specific metadata

    Design Philosophy:
    - content: For LLM reasoning (string representation)
    - metadata: For system/frontend consumption (structured data)
    - All diagnostic data goes into metadata for unified access

    Usage in tools:
        @tool
        async def my_tool(...) -> ToolResult:
            result_data = {"key": "value", "rows": [...]}
            return ToolResult(
                content="Found 10 records",  # For LLM
                metadata={
                    "raw_result": result_data,  # For frontend/debugging
                    "execution_time_ms": 123,
                }
            )

    Usage in capability wrappers:
        return ToolResult(
            content=final_message.content,
            metadata={
                "raw_result": result,  # Original agent result
            }
        )
    """

    content: str
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    error: ToolError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _coerce_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False, default=str)
        except Exception:
            return str(content)

    @classmethod
    def success(cls, content: Any, metadata: dict[str, Any] | None = None) -> "ToolResult":
        return cls(content=cls._coerce_content(content), status=ToolResultStatus.SUCCESS, metadata=metadata or {})

    @classmethod
    def error_result(
        cls,
        message: Any,
        *,
        code: str | ToolErrorCode = ToolErrorCode.TOOL_EXECUTION_ERROR,
        retryable: bool = False,
        hint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        message_text = cls._coerce_content(message)
        return cls(
            content=message_text,
            status=ToolResultStatus.ERROR,
            error=ToolError(code=str(code), message=message_text, retryable=retryable, hint=hint),
            metadata=metadata or {},
        )

    @classmethod
    def skipped(
        cls,
        content: Any,
        *,
        code: ToolSkipCode | str = ToolSkipCode.TOOL_SKIPPED,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        message_text = cls._coerce_content(content)
        skip_code = code if isinstance(code, ToolSkipCode) else ToolSkipCode(code)
        return cls(
            content=message_text,
            status=ToolResultStatus.SKIPPED,
            metadata={**(metadata or {}), SKIP_CODE_KEY: skip_code},
        )

    def __str__(self) -> str:
        """Return content for backward compatibility with StructuredTool."""
        return str(self.content)
