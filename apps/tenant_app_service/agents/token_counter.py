"""Token counting utility for message management."""

import json

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool


def estimate_tool_chars(tools: list[BaseTool]) -> int:
    """Estimate character count for tool definitions sent to LLM.

    LangChain converts tools to JSON schema format when sending to the API.
    This approximates that serialization to estimate character usage.
    The caller is responsible for converting characters to tokens.

    Args:
        tools: List of LangChain tools

    Returns:
        Estimated character count for all tool definitions
    """
    if not tools:
        return 0

    total_chars = 0

    for tool in tools:
        # Tool name
        total_chars += len(tool.name)

        # Tool description
        if tool.description:
            total_chars += len(tool.description)

        # Tool args_schema (Pydantic model converted to JSON schema)
        if tool.args_schema:
            try:
                # Get JSON schema representation
                schema = tool.args_schema.model_json_schema()
                schema_json = json.dumps(schema, ensure_ascii=False)
                total_chars += len(schema_json)
            except Exception:
                # Fallback: estimate based on model fields
                if hasattr(tool.args_schema, "model_fields"):
                    total_chars += len(str(tool.args_schema.model_fields)) * 2

    return total_chars


def count_tokens(
    messages: list[BaseMessage],
    system_prompt: str | None = None,
    tools: list[BaseTool] | None = None,
) -> int:
    """Count total tokens in a list of messages.

    Counts:
    - System prompt (if provided)
    - Tool definitions (if provided)
    - Message content (text)
    - Tool calls (for AIMessage)
    - Additional kwargs (metadata, tool_call_id, etc.)

    Uses a simple heuristic: ~4 characters per token.
    For production use, integrate with tiktoken or model-specific tokenizers.

    Args:
        messages: List of LangChain messages
        system_prompt: Optional system prompt to include in token count
        tools: Optional list of tools whose definitions are sent to LLM

    Returns:
        Estimated token count
    """
    total_chars = 0

    # Count system prompt if provided
    if system_prompt:
        total_chars += len(system_prompt)

    # Count tool definitions if provided
    if tools:
        total_chars += estimate_tool_chars(tools)

    for msg in messages:
        # Count content
        if hasattr(msg, "content") and msg.content:
            total_chars += len(str(msg.content))

        # Count tool_calls (AIMessage with tool_calls)
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            # Serialize tool_calls to JSON to estimate token count
            tool_calls_json = json.dumps(msg.tool_calls, ensure_ascii=False)
            total_chars += len(tool_calls_json)

        # Count additional_kwargs (timestamps, metadata, etc.)
        if hasattr(msg, "additional_kwargs") and msg.additional_kwargs:
            # Only count substantial fields (skip internal tracking fields)
            kwargs_to_count = {k: v for k, v in msg.additional_kwargs.items()}
            if kwargs_to_count:
                kwargs_json = json.dumps(kwargs_to_count, ensure_ascii=False)
                total_chars += len(kwargs_json)

        # Count tool_call_id (ToolMessage)
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            total_chars += len(msg.tool_call_id)

    return total_chars // 4
