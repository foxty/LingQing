"""Tests for LLM token usage extraction, model labels, and event mapping."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from apps.shared.observability.adapters import db_model_to_event, event_to_db_model
from apps.shared.observability.domain import (
    AgentSessionMetrics,
    EventType,
    MetricsContext,
    MetricsEvent,
    TokenUsage,
    format_model_label,
)
from apps.shared.observability.service import ObservabilityService
from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
    _extract_token_usage,
    llm_call_tracker,
)


def test_format_model_label_shows_routing_when_ids_differ():
    assert (
        format_model_label("system.ai.deepseek-v4-flash-0731", "/mosaicml/local_model")
        == "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model"
    )


def test_format_model_label_uses_single_identifier():
    assert format_model_label("system.ai.deepseek-v4-flash-0731", "system.ai.deepseek-v4-flash-0731") == (
        "system.ai.deepseek-v4-flash-0731"
    )
    assert format_model_label("system.ai.deepseek-v4-flash-0731", None) == "system.ai.deepseek-v4-flash-0731"
    assert format_model_label(None, "/mosaicml/local_model") == "/mosaicml/local_model"
    assert format_model_label(None, None) is None


def test_extract_token_usage_prefers_raw_response_metadata():
    response = AIMessage(
        content="ok",
        response_metadata={
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
            }
        },
        usage_metadata={
            "input_tokens": 999,
            "output_tokens": 888,
            "total_tokens": 1887,
        },
    )

    usage, extra = _extract_token_usage(response)

    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
    assert usage.total_tokens == 150
    assert extra["usage_diagnostics"]["usage_source"] == "response_metadata.usage"
    assert extra["usage_diagnostics"]["input_tokens_source_mismatch"] is True


def test_extract_token_usage_reads_token_usage_alias():
    response = AIMessage(
        content="ok",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 100,
            }
        },
    )

    usage, extra = _extract_token_usage(response)

    assert usage.input_tokens == 80
    assert usage.output_tokens == 20
    assert extra["usage_diagnostics"]["usage_source"] == "response_metadata.usage"


def test_extract_token_usage_keeps_provider_values_without_adjustment():
    provider_input = 125_118
    response = AIMessage(
        content="summary",
        response_metadata={
            "usage": {
                "prompt_tokens": provider_input,
                "completion_tokens": 16,
                "total_tokens": provider_input + 16,
            }
        },
    )

    usage, extra = _extract_token_usage(response)

    assert usage.input_tokens == provider_input
    assert usage.output_tokens == 16
    assert extra["usage_diagnostics"]["usage_source"] == "response_metadata.usage"


def test_extract_token_usage_flags_streaming_inflation_without_changing_values():
    response = AIMessage(
        content="x" * 400,
        usage_metadata={
            "input_tokens": 28358432,
            "output_tokens": 582175,
            "total_tokens": 28940607,
        },
    )

    usage, extra = _extract_token_usage(response, max_output_tokens=4000)

    assert usage.input_tokens == 28358432
    assert usage.output_tokens == 582175
    diagnostics = extra["usage_diagnostics"]
    assert diagnostics["missing_raw_usage"] is True
    assert diagnostics["output_exceeds_max_tokens"] is True


def test_extract_token_usage_falls_back_to_usage_metadata():
    response = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 20_644,
            "output_tokens": 1_266,
            "total_tokens": 21_910,
        },
    )

    usage, extra = _extract_token_usage(response)

    assert usage.input_tokens == 20_644
    assert usage.output_tokens == 1_266
    assert extra["usage_diagnostics"]["usage_source"] == "usage_metadata"


def test_extract_token_usage_returns_zeros_when_missing():
    usage, extra = _extract_token_usage(AIMessage(content="ok"))

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert extra["usage_diagnostics"]["usage_source"] == "none"


def test_session_metrics_aggregate_by_model_label():
    now = datetime.now(UTC)
    events = [
        MetricsEvent(
            event_type=EventType.LLM_CALL,
            context=MetricsContext(
                session_id="s-1",
                model_key="system.ai.deepseek-v4-flash-0731",
                model_name="/mosaicml/local_model",
            ),
            start_time=now,
            end_time=now,
            token_usage=TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
        )
    ]

    metrics = AgentSessionMetrics.from_events(events)

    assert metrics.total_tokens.input_tokens == 100
    assert metrics.total_tokens.total_tokens == 110
    assert "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model" in metrics.model_usage


def test_session_metrics_aggregate_thinking_from_llm_events():
    now = datetime.now(UTC)
    events = [
        MetricsEvent(
            event_type=EventType.LLM_CALL,
            context=MetricsContext(session_id="s-thinking", model_key="qwen3.5-plus"),
            start_time=now,
            end_time=now,
            extra_context={
                "thinking": {
                    "thinking_effort": "medium",
                    "supports_thinking": True,
                    "thinking_evidence": "usage",
                    "reasoning_tokens": 512,
                }
            },
        )
    ]

    metrics = AgentSessionMetrics.from_events(events)

    assert metrics.thinking is not None
    assert metrics.thinking["thinking_effort"] == "medium"
    assert metrics.thinking["reasoning_tokens"] == 512


def test_db_adapter_preserves_extra_context():
    now = datetime.now(UTC)
    event = MetricsEvent(
        event_type=EventType.LLM_CALL,
        context=MetricsContext(
            session_id="s-1",
            model_key="system.ai.deepseek-v4-flash-0731",
            model_name="/mosaicml/local_model",
        ),
        start_time=now,
        end_time=now,
        token_usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        extra_context={"model_label": "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model"},
    )

    restored = db_model_to_event(event_to_db_model(event))

    assert restored.extra_context["model_label"] == "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model"
    assert restored.token_usage.input_tokens == 10


def test_db_adapter_preserves_usage_details_in_extra_context():
    now = datetime.now(UTC)
    event = MetricsEvent(
        event_type=EventType.LLM_CALL,
        context=MetricsContext(session_id="s-usage-details"),
        start_time=now,
        end_time=now,
        token_usage=TokenUsage(input_tokens=500, output_tokens=50, total_tokens=550),
        extra_context={
            "usage_details": {
                "cache_read_input_tokens": 400,
                "cache_creation_input_tokens": 25,
                "reasoning_tokens": 12,
            },
            "usage_diagnostics": {"usage_source": "response_metadata.usage"},
        },
    )

    restored = db_model_to_event(event_to_db_model(event))

    assert restored.extra_context["usage_details"]["cache_read_input_tokens"] == 400
    assert restored.extra_context["usage_details"]["cache_creation_input_tokens"] == 25
    assert restored.extra_context["usage_details"]["reasoning_tokens"] == 12
    assert restored.token_usage.input_tokens == 500


@pytest.mark.asyncio
async def test_token_events_use_stored_or_computed_model_label():
    now = datetime.now(UTC)
    events = [
        MetricsEvent(
            event_id="e-1",
            event_type=EventType.LLM_CALL,
            context=MetricsContext(
                session_id="s-1",
                model_key="system.ai.deepseek-v4-flash-0731",
                model_name="/mosaicml/local_model",
            ),
            start_time=now,
            end_time=now,
            timestamp=now,
            token_usage=TokenUsage(input_tokens=21_778, output_tokens=2_255, total_tokens=24_033),
            extra_context={
                "model_label": "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model",
                "usage_details": {"cache_read_input_tokens": 10_000, "reasoning_tokens": 200},
            },
        )
    ]
    repo = SimpleNamespace(
        count_events_by_filters=AsyncMock(return_value=1),
        get_events_page_by_filters=AsyncMock(return_value=events),
    )

    total, rows = await ObservabilityService(repo).get_tenant_token_events(
        tenant_id=2,
        start_time=now,
        end_time=now,
    )

    assert total == 1
    assert rows[0]["model_label"] == "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model"
    assert rows[0]["input_tokens"] == 21_778
    assert rows[0]["total_tokens"] == 24_033
    assert rows[0]["cache_read_input_tokens"] == 10_000
    assert rows[0]["reasoning_tokens"] == 200


@pytest.mark.asyncio
async def test_llm_tracker_persists_provider_usage_and_model_label(runtime_context, monkeypatch):
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    memory_storage._events.clear()
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    async with llm_call_tracker(
        "yaml-model",
        runtime_context,
        configured_model_id="system.ai.deepseek-v4-flash-0731",
        max_output_tokens=4000,
    ) as tracker:
        tracker.record_response(
            AIMessage(
                content="hi",
                response_metadata={
                    "model_name": "/mosaicml/local_model",
                    "usage": {
                        "prompt_tokens": 21778,
                        "completion_tokens": 2255,
                        "total_tokens": 24033,
                    },
                },
            )
        )

    events = memory_storage._events.get(runtime_context.session_id, [])
    assert len(events) == 1
    event = events[0]
    assert event.token_usage.input_tokens == 21778
    assert event.token_usage.output_tokens == 2255
    assert event.context.model_key == "system.ai.deepseek-v4-flash-0731"
    assert event.context.model_name == "/mosaicml/local_model"
    assert event.extra_context["model_label"] == "system.ai.deepseek-v4-flash-0731 → /mosaicml/local_model"
    assert event.extra_context["usage_diagnostics"]["usage_source"] == "response_metadata.usage"
    assert "usage_details" not in event.extra_context


@pytest.mark.asyncio
async def test_llm_tracker_persists_usage_details_when_provider_reports_breakdown(
    runtime_context, monkeypatch
):
    from apps.tenant_app_service.agents.metrics import agent_metrics_instrumentation
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    memory_storage = get_storage("memory")
    memory_storage._events.clear()
    monkeypatch.setattr(agent_metrics_instrumentation, "get_metrics_storage", lambda: memory_storage)

    async with llm_call_tracker("yaml-model", runtime_context) as tracker:
        tracker.record_response(
            AIMessage(
                content="hi",
                response_metadata={
                    "usage": {
                        "prompt_tokens": 1000,
                        "completion_tokens": 80,
                        "total_tokens": 1080,
                        "prompt_tokens_details": {"cached_tokens": 900},
                        "completion_tokens_details": {"reasoning_tokens": 26},
                    }
                },
            )
        )

    event = memory_storage._events[runtime_context.session_id][0]
    assert event.extra_context["usage_details"]["cache_read_input_tokens"] == 900
    assert event.extra_context["usage_details"]["reasoning_tokens"] == 26
    assert event.token_usage.input_tokens == 1000
    assert event.token_usage.output_tokens == 80


@pytest.mark.asyncio
async def test_token_events_expose_breakdown_from_db_backed_extra_context():
    now = datetime.now(UTC)
    stored = MetricsEvent(
        event_id="e-db-1",
        event_type=EventType.LLM_CALL,
        context=MetricsContext(session_id="s-db"),
        start_time=now,
        end_time=now,
        timestamp=now,
        token_usage=TokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        extra_context={"usage_details": {"cache_read_input_tokens": 55, "reasoning_tokens": 7}},
    )
    round_tripped = db_model_to_event(event_to_db_model(stored))
    repo = SimpleNamespace(
        count_events_by_filters=AsyncMock(return_value=1),
        get_events_page_by_filters=AsyncMock(return_value=[round_tripped]),
    )

    _, rows = await ObservabilityService(repo).get_tenant_token_events(
        tenant_id=1,
        start_time=now,
        end_time=now,
    )

    assert rows[0]["cache_read_input_tokens"] == 55
    assert rows[0]["reasoning_tokens"] == 7
