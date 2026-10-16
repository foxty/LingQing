"""Tests for LLM message content normalization."""

from langchain_core.messages import AIMessage

from apps.tenant_app_service.agents.message_content import (
    EMPTY_LLM_RESPONSE_FALLBACK,
    ensure_visible_ai_content,
    extract_output_token_count,
    extract_thinking_content,
    extract_thinking_persistence_metadata,
    normalize_message_content,
)
from apps.tenant_app_service.agent_ingress.slack.domain import ensure_slack_reply_text


def test_normalize_message_content_string():
    assert normalize_message_content("hello") == "hello"


def test_normalize_message_content_text_blocks():
    content = [{"type": "text", "text": "Answer"}, {"type": "thinking", "thinking": "hidden"}]
    assert normalize_message_content(content) == "Answer"


def test_extract_thinking_content_from_blocks():
    content = [{"type": "thinking", "thinking": "step one"}, {"type": "text", "text": "Answer"}]
    assert extract_thinking_content(content) == "step one"


def test_extract_thinking_content_from_databricks_reasoning_blocks():
    content = [
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "Rayleigh scattering..."}],
        },
        {"type": "text", "text": "Answer"},
    ]
    assert extract_thinking_content(content) == "Rayleigh scattering..."


def test_ensure_visible_ai_content_preserves_thinking_in_kwargs():
    content = [{"type": "thinking", "thinking": "chain"}, {"type": "text", "text": "Answer"}]
    response = AIMessage(content=content)
    result = ensure_visible_ai_content(response)
    assert result.content == "Answer"
    assert result.additional_kwargs.get("thinking_content") == "chain"


def test_persistence_metadata_reasoning_tokens_without_content_blocks():
    response = AIMessage(
        content="Hello",
        response_metadata={
            "usage": {
                "completion_tokens": 102,
                "completion_tokens_details": {"reasoning_tokens": 26},
            }
        },
    )
    meta = extract_thinking_persistence_metadata(response)
    assert meta["reasoning_tokens"] == 26
    assert meta["thinking_evidence"] == "usage"
    assert "thinking_content" not in meta


def test_ensure_visible_ai_content_stores_usage_reasoning_on_kwargs():
    response = AIMessage(
        content="Hello",
        response_metadata={"usage": {"reasoning_tokens": 5}},
    )
    result = ensure_visible_ai_content(response)
    assert result.additional_kwargs.get("reasoning_tokens") == 5
    assert result.additional_kwargs.get("thinking_evidence") == "usage"


def test_normalize_message_content_empty_list():
    assert normalize_message_content([]) == ""


def test_extract_output_token_count_from_usage_metadata():
    response = AIMessage(
        content="",
        usage_metadata={"input_tokens": 1, "output_tokens": 778, "total_tokens": 779},
    )
    assert extract_output_token_count(response) == 778


def test_ensure_visible_ai_content_applies_fallback_for_empty_response():
    response = AIMessage(
        content="",
        usage_metadata={"input_tokens": 1, "output_tokens": 10, "total_tokens": 11},
    )
    result = ensure_visible_ai_content(response)
    assert result.content == EMPTY_LLM_RESPONSE_FALLBACK


def test_ensure_visible_ai_content_keeps_tool_only_response_empty():
    response = AIMessage(content="", tool_calls=[{"id": "1", "name": "query", "args": {}}])
    result = ensure_visible_ai_content(response)
    assert result.content == ""


def test_ensure_slack_reply_text_fallback():
    assert ensure_slack_reply_text("   ") == "The model returned no visible text. Please try again."
