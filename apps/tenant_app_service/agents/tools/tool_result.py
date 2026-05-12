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
        code: str = "TOOL_EXECUTION_ERROR",
        retryable: bool = False,
        hint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        message_text = cls._coerce_content(message)
        return cls(
            content=message_text,
            status=ToolResultStatus.ERROR,
            error=ToolError(code=code, message=message_text, retryable=retryable, hint=hint),
            metadata=metadata or {},
        )

    def __str__(self) -> str:
        """Return content for backward compatibility with StructuredTool."""
        return str(self.content)
