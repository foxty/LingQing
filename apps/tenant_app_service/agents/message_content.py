"""Helpers for normalizing LangChain message content to displayable text."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

EMPTY_LLM_RESPONSE_FALLBACK = "The model returned no visible text. Please try again."

_TEXT_BLOCK_TYPES = frozenset({"text", "output_text", "input_text"})


def extract_thinking_content(content: Any) -> str:
    """Extract provider reasoning/thinking text for UI (not sent back to the LLM)."""
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "thinking":
            text = block.get("thinking") or block.get("text") or block.get("content") or ""
            if str(text).strip():
                parts.append(str(text).strip())
        elif block_type == "reasoning":
            summary = block.get("summary")
            if isinstance(summary, list):
                for item in summary:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content") or ""
                        if str(text).strip():
                            parts.append(str(text).strip())
            else:
                text = block.get("text") or block.get("content") or ""
                if str(text).strip():
                    parts.append(str(text).strip())
    return "\n\n".join(parts)


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
                elif block_type in ("thinking", "reasoning"):
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


def _raw_provider_usage(response: AIMessage) -> dict[str, Any]:
    """Provider usage dict from LangChain AIMessage (OpenAI-compatible shape)."""
    response_metadata = getattr(response, "response_metadata", None) or {}
    usage = response_metadata.get("usage")
    if isinstance(usage, dict) and usage:
        return usage
    token_usage = response_metadata.get("token_usage")
    if isinstance(token_usage, dict) and token_usage:
        return token_usage
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    if isinstance(usage_metadata, dict) and usage_metadata:
        mapped: dict[str, Any] = dict(usage_metadata)
        if "output_tokens" in mapped and "completion_tokens" not in mapped:
            mapped["completion_tokens"] = mapped["output_tokens"]
        return mapped
    return {}


def extract_thinking_persistence_metadata(response: AIMessage) -> dict[str, Any]:
    """Reasoning/thinking fields for message_metadata (see THINKING_MESSAGE_METADATA_KEYS)."""
    if not isinstance(response, AIMessage):
        return {}

    meta: dict[str, Any] = {}

    thinking_text = extract_thinking_content(response.content)
    if thinking_text:
        meta["thinking_content"] = thinking_text

    raw_usage = _raw_provider_usage(response)
    details = raw_usage.get("completion_tokens_details")
    if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
        meta["reasoning_tokens"] = int(details["reasoning_tokens"])
        meta["thinking_evidence"] = "usage"
    for key in ("reasoning_tokens", "thoughts_tokens"):
        if key in raw_usage and raw_usage[key] is not None:
            meta["reasoning_tokens"] = int(raw_usage[key])
            meta["thinking_evidence"] = "usage"
            break

    content = getattr(response, "content", None)
    if isinstance(content, list):
        block_count = sum(
            1
            for block in content
            if isinstance(block, dict) and block.get("type") in ("thinking", "reasoning")
        )
        if block_count:
            meta["thinking_content_blocks"] = block_count
            meta["thinking_evidence"] = "content_blocks"

    return meta


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
    persistence = extract_thinking_persistence_metadata(response)
    if persistence:
        kwargs = dict(response.additional_kwargs or {})
        kwargs.update(persistence)
        response.additional_kwargs = kwargs
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
