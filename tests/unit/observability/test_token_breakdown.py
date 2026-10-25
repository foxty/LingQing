"""Tests for token usage breakdown (cache read, reasoning)."""

from datetime import UTC, datetime

from langchain_core.messages import AIMessage

from apps.shared.observability.domain import EventType, MetricsContext, MetricsEvent, TokenUsage
from apps.shared.observability.token_breakdown import (
    parse_usage_breakdown,
    token_event_breakdown_from_event,
)
from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import _extract_token_usage


def test_parse_usage_breakdown_openai_cached_tokens():
    raw = {
        "prompt_tokens": 500,
        "completion_tokens": 50,
        "total_tokens": 550,
        "prompt_tokens_details": {"cached_tokens": 400},
        "completion_tokens_details": {"reasoning_tokens": 12},
    }
    breakdown = parse_usage_breakdown(raw, {})
    assert breakdown["cache_read_input_tokens"] == 400
    assert breakdown["reasoning_tokens"] == 12


def test_parse_usage_breakdown_anthropic_cache_read():
    raw = {
        "input_tokens": 1000,
        "output_tokens": 80,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 50,
    }
    breakdown = parse_usage_breakdown(raw, {})
    assert breakdown["cache_read_input_tokens"] == 900
    assert breakdown["cache_creation_input_tokens"] == 50


def test_extract_token_usage_persists_usage_details_in_extra():
    response = AIMessage(
        content="ok",
        response_metadata={
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 30,
                "total_tokens": 230,
                "prompt_tokens_details": {"cached_tokens": 150},
                "completion_tokens_details": {"reasoning_tokens": 8},
            }
        },
    )
    usage, extra = _extract_token_usage(response)
    assert usage.input_tokens == 200
    assert usage.output_tokens == 30
    assert extra["usage_details"]["cache_read_input_tokens"] == 150
    assert extra["usage_details"]["reasoning_tokens"] == 8


def test_token_event_breakdown_from_stored_usage_details():
    now = datetime.now(UTC)
    event = MetricsEvent(
        event_type=EventType.LLM_CALL,
        context=MetricsContext(session_id="s-1"),
        start_time=now,
        end_time=now,
        token_usage=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        extra_context={"usage_details": {"cache_read_input_tokens": 60, "reasoning_tokens": 5}},
    )
    breakdown = token_event_breakdown_from_event(event)
    assert breakdown["cache_read_input_tokens"] == 60
    assert breakdown["reasoning_tokens"] == 5


def test_token_event_breakdown_falls_back_to_thinking_extra():
    now = datetime.now(UTC)
    event = MetricsEvent(
        event_type=EventType.LLM_CALL,
        context=MetricsContext(session_id="s-1"),
        start_time=now,
        end_time=now,
        extra_context={"thinking": {"reasoning_tokens": 512}},
    )
    breakdown = token_event_breakdown_from_event(event)
    assert breakdown["cache_read_input_tokens"] is None
    assert breakdown["reasoning_tokens"] == 512


def test_parse_usage_breakdown_langchain_input_output_token_details():
    """LangChain-normalized usage_metadata (no raw OpenAI usage dict)."""
    metadata = {
        "input_tokens": 300,
        "output_tokens": 40,
        "input_token_details": {
            "cache_read": 220,
            "cache_creation": 15,
        },
        "output_token_details": {"reasoning_tokens": 18},
    }
    breakdown = parse_usage_breakdown({}, metadata)
    assert breakdown["cache_read_input_tokens"] == 220
    assert breakdown["cache_creation_input_tokens"] == 15
    assert breakdown["reasoning_tokens"] == 18


def test_parse_usage_breakdown_langchain_input_details_long_keys():
    metadata = {
        "input_token_details": {
            "cache_read_input_tokens": 111,
            "cache_creation_input_tokens": 22,
        }
    }
    breakdown = parse_usage_breakdown({}, metadata)
    assert breakdown["cache_read_input_tokens"] == 111
    assert breakdown["cache_creation_input_tokens"] == 22


def test_parse_usage_breakdown_top_level_reasoning_tokens():
    raw = {"completion_tokens": 50, "reasoning_tokens": 33}
    breakdown = parse_usage_breakdown(raw, {})
    assert breakdown["reasoning_tokens"] == 33


def test_parse_usage_breakdown_thoughts_tokens_alias():
    raw = {"completion_tokens": 50, "thoughts_tokens": 44}
    breakdown = parse_usage_breakdown(raw, {})
    assert breakdown["reasoning_tokens"] == 44


def test_parse_usage_breakdown_prefers_completion_details_over_top_level_reasoning():
    raw = {
        "completion_tokens_details": {"reasoning_tokens": 10},
        "reasoning_tokens": 99,
    }
    breakdown = parse_usage_breakdown(raw, {})
    assert breakdown["reasoning_tokens"] == 10


def test_parse_usage_breakdown_prefers_openai_cached_over_langchain_metadata():
    raw = {"prompt_tokens_details": {"cached_tokens": 100}}
    metadata = {"input_token_details": {"cache_read": 999}}
    breakdown = parse_usage_breakdown(raw, metadata)
    assert breakdown["cache_read_input_tokens"] == 100


def test_parse_usage_breakdown_openai_token_usage_alias():
    """response_metadata.token_usage shape (same fields as usage)."""
    raw = {
        "prompt_tokens": 80,
        "completion_tokens": 20,
        "prompt_tokens_details": {"cached_tokens": 60},
    }
    breakdown = parse_usage_breakdown(raw, {})
    assert breakdown["cache_read_input_tokens"] == 60


def test_parse_usage_breakdown_empty_when_no_signals():
    assert parse_usage_breakdown({}, {}) == {}


def test_extract_token_usage_usage_metadata_only_with_breakdown():
    response = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 75, "cache_creation": 5},
            "output_token_details": {"reasoning_tokens": 15},
        },
    )
    usage, extra = _extract_token_usage(response)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert extra["usage_diagnostics"]["usage_source"] == "usage_metadata"
    assert extra["usage_details"]["cache_read_input_tokens"] == 75
    assert extra["usage_details"]["cache_creation_input_tokens"] == 5
    assert extra["usage_details"]["reasoning_tokens"] == 15


def test_token_event_breakdown_prefers_usage_details_over_thinking():
    now = datetime.now(UTC)
    event = MetricsEvent(
        event_type=EventType.LLM_CALL,
        context=MetricsContext(session_id="s-1"),
        start_time=now,
        end_time=now,
        extra_context={
            "usage_details": {"reasoning_tokens": 20},
            "thinking": {"reasoning_tokens": 512},
        },
    )
    breakdown = token_event_breakdown_from_event(event)
    assert breakdown["reasoning_tokens"] == 20
