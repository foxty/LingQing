"""Tests for LLM message content normalization."""

from langchain_core.messages import AIMessage

from apps.tenant_app_service.agents.message_content import (
    EMPTY_LLM_RESPONSE_FALLBACK,
    ensure_visible_ai_content,
    extract_output_token_count,
    normalize_message_content,
)
from apps.tenant_app_service.slack.domain import ensure_slack_reply_text


def test_normalize_message_content_string():
    assert normalize_message_content("hello") == "hello"


def test_normalize_message_content_text_blocks():
    content = [{"type": "text", "text": "Answer"}, {"type": "thinking", "thinking": "hidden"}]
    assert normalize_message_content(content) == "Answer"


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
