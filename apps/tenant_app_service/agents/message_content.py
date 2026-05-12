"""Helpers for normalizing LangChain message content to displayable text."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

EMPTY_LLM_RESPONSE_FALLBACK = "The model returned no visible text. Please try again."

_TEXT_BLOCK_TYPES = frozenset({"text", "output_text", "input_text"})


def normalize_message_content(content: Any) -> str:
    """Extract user-visible text from LangChain message content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                if block.strip():
                    parts.append(block)
                continue
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type in _TEXT_BLOCK_TYPES:
                    text = block.get("text") or block.get("content") or ""
                    if str(text).strip():
                        parts.append(str(text))
                elif block_type == "thinking":
                    continue
                elif block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("content"):
                    parts.append(str(block["content"]))
                continue
            text = getattr(block, "text", None) or getattr(block, "content", None)
            if text and str(text).strip():
                parts.append(str(text))
        return "\n".join(parts).strip()
    text = str(content).strip()
    return "" if text in ("[]", "{}") else text


def extract_output_token_count(response: AIMessage) -> int:
    """Read completion/output token count from a LangChain AIMessage."""
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    output_tokens = usage_metadata.get("output_tokens") or usage_metadata.get("completion_tokens") or 0
    if output_tokens:
        return int(output_tokens)

    response_metadata = getattr(response, "response_metadata", None) or {}
    usage = response_metadata.get("usage") or {}
    completion_tokens = usage.get("completion_tokens") or response_metadata.get("completion_tokens") or 0
    return int(completion_tokens or 0)


def ensure_visible_ai_content(response: AIMessage) -> AIMessage:
    """Normalize AI content and apply a fallback when the model returns no usable text."""
    normalized = normalize_message_content(response.content)
    response.content = normalized

    tool_calls = getattr(response, "tool_calls", None) or []
    if normalized.strip() or tool_calls:
        return response

    output_tokens = extract_output_token_count(response)
    logger.warning(
        "LLM returned no visible text (output_tokens=%s, tool_calls=%s, message_id=%s)",
        output_tokens,
        len(tool_calls),
        getattr(response, "id", None),
    )
    response.content = EMPTY_LLM_RESPONSE_FALLBACK
    return response
