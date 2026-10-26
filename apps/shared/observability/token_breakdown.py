"""Best-effort token breakdown (cache read, reasoning) from provider usage payloads."""

from __future__ import annotations

from typing import Any

from apps.shared.observability.domain import MetricsEvent


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_usage_breakdown(
    raw_usage: dict[str, Any],
    usage_metadata: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Extract non-billed-extra breakdown fields from provider usage.

    Values are subsets of provider-reported input/output totals, not additive.
    """
    usage_metadata = usage_metadata or {}
    cache_read: int | None = None
    cache_creation: int | None = None
    reasoning: int | None = None

    prompt_details = raw_usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        cache_read = _int_or_none(prompt_details.get("cached_tokens"))

    if cache_read is None:
        cache_read = _int_or_none(raw_usage.get("cache_read_input_tokens"))
    cache_creation = _int_or_none(raw_usage.get("cache_creation_input_tokens"))

    if cache_read is None:
        input_details = usage_metadata.get("input_token_details")
        if isinstance(input_details, dict):
            cache_read = _int_or_none(
                input_details.get("cache_read") or input_details.get("cache_read_input_tokens")
            )
            if cache_creation is None:
                cache_creation = _int_or_none(
                    input_details.get("cache_creation") or input_details.get("cache_creation_input_tokens")
                )

    completion_details = raw_usage.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        reasoning = _int_or_none(completion_details.get("reasoning_tokens"))
    for key in ("reasoning_tokens", "thoughts_tokens"):
        if reasoning is None and key in raw_usage:
            reasoning = _int_or_none(raw_usage[key])

    if reasoning is None:
        output_details = usage_metadata.get("output_token_details")
        if isinstance(output_details, dict):
            reasoning = _int_or_none(output_details.get("reasoning_tokens"))

    breakdown: dict[str, int] = {}
    if cache_read is not None:
        breakdown["cache_read_input_tokens"] = cache_read
    if cache_creation is not None:
        breakdown["cache_creation_input_tokens"] = cache_creation
    if reasoning is not None:
        breakdown["reasoning_tokens"] = reasoning
    return breakdown


def token_event_breakdown_from_event(event: MetricsEvent) -> dict[str, int | None]:
    """Breakdown fields for token event APIs (supports legacy events via thinking extra)."""
    extra = event.extra_context or {}
    cache_read: int | None = None
    reasoning: int | None = None

    details = extra.get("usage_details")
    if isinstance(details, dict):
        cache_read = _int_or_none(details.get("cache_read_input_tokens"))
        reasoning = _int_or_none(details.get("reasoning_tokens"))

    if reasoning is None:
        thinking = extra.get("thinking")
        if isinstance(thinking, dict):
            reasoning = _int_or_none(thinking.get("reasoning_tokens"))

    return {
        "cache_read_input_tokens": cache_read,
        "reasoning_tokens": reasoning,
    }
