"""Non-intrusive instrumentation for agent metrics collection (V3).

This module provides decorators and context managers to automatically collect
metrics without modifying agent code logic. Uses V3 event-based architecture.

Key features:
- Zero-intrusion: Apply decorators without changing method logic
- Automatic context: Extracts RuntimeContext from RunnableConfig
- Event-driven: Each call produces immutable events
- Async-safe: Works with both sync and async methods

Usage:
    # Apply to agent methods
    class AgentBase:
        @track_llm_call
        async def _llm_call(self, state, config):
            # Your existing logic unchanged
            response = await model.ainvoke(...)
            return {"messages": [response]}

        @track_tool_execution
        async def _tool_node(self, state, config):
            # Your existing logic unchanged
            results = await tool.ainvoke(...)
            return {"messages": results}
"""

import json
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage

from apps.config import EnvConfig
from apps.shared.observability.domain import format_model_label
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, PromptContextStats
from apps.tenant_app_service.agents.metrics.agent_metrics_v3 import (
    CallStatus,
    EventType,
    MetricsContext,
    MetricsEvent,
    TokenUsage,
)
from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import MetricsStorage, get_storage

logger = get_logger(__name__)


def _naive_utc_from_ts(timestamp: float) -> datetime:
    """Convert unix timestamp to naive UTC datetime for DB storage."""
    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)


def _naive_utc_now() -> datetime:
    """Current naive UTC datetime for DB storage."""
    return datetime.now(UTC).replace(tzinfo=None)

# ============ Storage Access ============


def get_metrics_storage(backend: str = "database") -> MetricsStorage:
    """Get the metrics storage instance.

    Args:
        backend: Storage backend ("memory" or "database")

    Returns:
        MetricsStorage instance
    """
    return get_storage(backend)


# ============ Context Extraction Helpers ============


def _serialize_to_string(obj: Any) -> str:
    """Serialize object to string, trying JSON first, then fallback to str().

    Args:
        obj: Object to serialize

    Returns:
        Serialized string representation
    """
    try:
        # Try JSON serialization first (preserves structure)
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        # Fallback to str() if JSON serialization fails
        try:
            return str(obj)
        except Exception:
            return "<unable to serialize>"


def _truncate_preview(content: str, max_length: int | None = None) -> str:
    """Truncate content for preview based on configuration.

    Args:
        content: Content to truncate
        max_length: Maximum length (None = use env config, 0 = disabled, -1 = unlimited)

    Returns:
        Truncated content or empty string if disabled
    """
    if max_length is None:
        max_length = EnvConfig.METRICS_PREVIEW_MAX_LENGTH

    if max_length == 0:
        return ""  # Disabled
    if max_length == -1:
        return content  # Unlimited

    return content[:max_length] if len(content) > max_length else content


def _extract_metrics_context(context: AgentRuntimeContext) -> MetricsContext:
    """Extract MetricsContext from AgentRuntimeContext.

    Args:
        context: Agent runtime context with user, agent, session info

    Returns:
        MetricsContext for event tracking
    """
    return MetricsContext(
        session_id=context.session_id,
        thread_id=context.thread_id or "",
        tenant_id=context.user.tenant_id,
        tenant_name=context.user.tenant_name,
        agent_id=context.agent_id,
        agent_name=context.agent_name,
        user_id=context.user.user_id,
        username=context.user.username,
    )


# ============ Context Managers for Metrics Tracking ============


@asynccontextmanager
async def llm_call_tracker(
    model_key: str,
    context: AgentRuntimeContext,
    prompt_context_stats: PromptContextStats | None = None,
    configured_model_id: str | None = None,
    max_output_tokens: int | None = None,
):
    """Context manager for tracking LLM calls.

    Args:
        model_key: Model identifier for tracking
        context: Agent runtime context with user, agent, session info
        prompt_context_stats: Optional prompt-context stats to persist in event context

    Usage:
        # In AgentBase nodes
        runtime = extract_runtime_context(config)
        async with llm_call_tracker(model_key, runtime) as tracker:
            response = await model.ainvoke(messages)
            tracker.record_response(response)

        # In MiniAgent
        async with llm_call_tracker(model_key, context) as tracker:
            response = await model.ainvoke(messages)
            tracker.record_response(response)
    """
    metrics_context = _extract_metrics_context(context)
    metrics_context.model_key = configured_model_id or model_key
    extra_context = {}
    if configured_model_id:
        extra_context["configured_model_id"] = configured_model_id
    if prompt_context_stats is not None:
        metrics_context.message_count = prompt_context_stats.final_count
        extra_context["message_prep"] = asdict(prompt_context_stats)
    start_timestamp = time.time()
    start_dt = _naive_utc_from_ts(start_timestamp)

    class Tracker:
        def __init__(self):
            self.response = None

        def record_response(self, response) -> AIMessage:
            self.response = response

    tracker = Tracker()

    try:
        yield tracker

        # Calculate end time
        end_timestamp = time.time()
        end_dt = _naive_utc_from_ts(end_timestamp)
        duration_ms = (end_timestamp - start_timestamp) * 1000

        # Create success event (response is the AIMessage)
        if tracker.response:
            token_usage, usage_extra = _extract_token_usage(
                tracker.response,
                max_output_tokens=max_output_tokens,
                session_id=metrics_context.session_id,
                model_key=metrics_context.model_key,
            )
            extra_context.update(usage_extra)
            tool_calls = _extract_tool_calls(tracker.response)
            response_model_name = _extract_model_name(tracker.response, model_key)
            metrics_context.model_name = response_model_name
            metrics_context.message_id = getattr(tracker.response, "id", None)
            if configured_model_id and response_model_name and configured_model_id != response_model_name:
                extra_context["response_model_name"] = response_model_name
            extra_context["model_label"] = format_model_label(
                metrics_context.model_key,
                response_model_name,
            )
            if tool_calls:
                metrics_context.has_tool_calls = True
                extra_context["tool_calls"] = tool_calls

            event = MetricsEvent(
                event_type=EventType.LLM_CALL,
                context=metrics_context,
                start_time=start_dt,
                end_time=end_dt,
                extra_context=extra_context,
                status=CallStatus.SUCCESS,
                token_usage=token_usage,
                duration_ms=duration_ms,
            )

            await get_metrics_storage().save_event(event)
        else:
            logger.warning("No response recorded in LLM call tracker")

    except Exception as e:
        logger.exception("Exception in LLM call tracking context manager")
        # Calculate end time for error case
        end_timestamp = time.time()
        end_dt = _naive_utc_from_ts(end_timestamp)
        duration_ms = (end_timestamp - start_timestamp) * 1000

        # Create error event (same event type, different status)
        event = MetricsEvent(
            event_type=EventType.LLM_CALL,
            context=metrics_context,
            start_time=start_dt,
            end_time=end_dt,
            status=CallStatus.ERROR,
            error_message=str(e),
            duration_ms=duration_ms,
        )

        await get_metrics_storage().save_event(event)
        raise


@asynccontextmanager
async def tool_call_tracker(
    tool_name: str,
    tool_call_id: str,
    tool_args: dict,
    context: AgentRuntimeContext,
):
    """Context manager for tracking individual tool executions.

    Args:
        tool_name: Name of the tool being called
        tool_call_id: Unique identifier for this tool call
        tool_args: Arguments passed to the tool
        context: Agent runtime context with user, agent, session info

    Usage:
        runtime = extract_runtime_context(config)
        async with tool_call_tracker(tool_name, call_id, args, runtime) as tracker:
            result = await tool.ainvoke(args, config)
            tracker.record_result(result)
    """
    metrics_context = _extract_metrics_context(context)
    extra_context = {}
    metrics_context.tool_call_id = tool_call_id
    metrics_context.tool_name = tool_name

    input_str = _serialize_to_string(tool_args)
    input_preview = _truncate_preview(input_str)
    if input_preview:  # Only add if not empty (i.e., not disabled)
        extra_context["tool_input_preview"] = input_preview
        extra_context["tool_input_size"] = len(input_str)

    start_timestamp = time.time()
    start_dt = _naive_utc_from_ts(start_timestamp)

    class Tracker:
        def __init__(self):
            self.result = None
            self.error = None

        def record_result(self, result):
            """Record successful tool result."""
            self.result = result

        def record_error(self, error: Exception):
            """Record tool error."""
            self.error = error

    tracker = Tracker()

    try:
        yield tracker

        # Calculate end time
        end_timestamp = time.time()
        end_dt = _naive_utc_from_ts(end_timestamp)
        duration_ms = (end_timestamp - start_timestamp) * 1000

        output_size = None
        if tracker.result is not None:
            output_str = _serialize_to_string(tracker.result)
            output_preview = _truncate_preview(output_str)
            if output_preview:  # Only add if not empty
                extra_context["tool_output_preview"] = output_preview
                extra_context["tool_output_size"] = len(output_str)
            output_size = len(output_str)

        if tracker.error is not None:
            event = MetricsEvent(
                event_type=EventType.TOOL_CALL,
                context=metrics_context,
                start_time=start_dt,
                end_time=end_dt,
                extra_context=extra_context,
                status=CallStatus.ERROR,
                error_message=str(tracker.error),
                input_size=len(input_str),
                output_size=output_size,
                duration_ms=duration_ms,
            )
            await get_metrics_storage().save_event(event)
        elif tracker.result is not None:
            event = MetricsEvent(
                event_type=EventType.TOOL_CALL,
                context=metrics_context,
                start_time=start_dt,
                end_time=end_dt,
                extra_context=extra_context,
                status=CallStatus.SUCCESS,
                input_size=len(input_str),
                output_size=output_size,
                duration_ms=duration_ms,
            )

            await get_metrics_storage().save_event(event)

    except Exception as e:
        # Calculate end time for error case
        end_timestamp = time.time()
        end_dt = _naive_utc_from_ts(end_timestamp)
        duration_ms = (end_timestamp - start_timestamp) * 1000

        # Create error event (same event type, different status)
        event = MetricsEvent(
            event_type=EventType.TOOL_CALL,
            context=metrics_context,
            start_time=start_dt,
            end_time=end_dt,
            status=CallStatus.ERROR,
            error_message=str(e),
            duration_ms=duration_ms,
        )

        await get_metrics_storage().save_event(event)
        raise


# ============ Helper Functions ============


def _extract_tool_calls(response: AIMessage) -> list[dict[str, Any]]:
    """Extract tool calls from LLM response."""
    tool_calls = getattr(response, "tool_calls", None)
    return tool_calls


def _raw_openai_usage(response: AIMessage) -> dict[str, Any]:
    """Read provider usage from AIMessage response metadata."""
    metadata = getattr(response, "response_metadata", None) or {}
    usage = metadata.get("usage")
    if isinstance(usage, dict) and usage:
        return usage
    token_usage = metadata.get("token_usage")
    if isinstance(token_usage, dict) and token_usage:
        return token_usage
    return {}


def _usage_from_raw(raw_usage: dict[str, Any]) -> TokenUsage:
    input_tokens = int(raw_usage.get("prompt_tokens") or 0)
    output_tokens = int(raw_usage.get("completion_tokens") or 0)
    total_tokens = raw_usage.get("total_tokens")
    total = int(total_tokens) if total_tokens is not None else input_tokens + output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
    )


def _usage_from_metadata(usage_metadata: dict[str, Any]) -> TokenUsage:
    input_tokens = int(usage_metadata.get("input_tokens") or 0)
    output_tokens = int(usage_metadata.get("output_tokens") or 0)
    total_tokens = usage_metadata.get("total_tokens")
    total = int(total_tokens) if total_tokens is not None else input_tokens + output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
    )


def _build_usage_diagnostics(
    provider: TokenUsage,
    *,
    usage_source: str,
    raw_usage: dict[str, Any],
    usage_metadata: dict[str, Any],
    max_output_tokens: int | None,
) -> dict[str, Any]:
    """Flag implausible usage without changing provider-reported values."""
    diagnostics: dict[str, Any] = {"usage_source": usage_source}

    if max_output_tokens is not None and provider.output_tokens > max_output_tokens:
        diagnostics["output_exceeds_max_tokens"] = True

    if usage_source == "usage_metadata" and provider.input_tokens > 0:
        diagnostics["missing_raw_usage"] = True

    if raw_usage and usage_metadata:
        metadata_input = int(usage_metadata.get("input_tokens") or 0)
        if metadata_input and metadata_input != provider.input_tokens:
            diagnostics["input_tokens_source_mismatch"] = True

    return diagnostics


def _log_usage_diagnostics(
    provider: TokenUsage,
    diagnostics: dict[str, Any],
    *,
    session_id: str | None,
    model_key: str | None,
) -> None:
    """Log usage anomalies; never mutate provider-reported counts."""
    anomaly_flags = (
        "output_exceeds_max_tokens",
        "missing_raw_usage",
        "input_tokens_source_mismatch",
    )
    if not any(diagnostics.get(flag) for flag in anomaly_flags):
        return

    logger.warning(
        "LLM token usage diagnostic session_id=%s model_key=%s "
        "provider_input=%s provider_output=%s provider_total=%s diagnostics=%s",
        session_id,
        model_key,
        provider.input_tokens,
        provider.output_tokens,
        provider.total_tokens,
        diagnostics,
    )


def _extract_token_usage(
    response: AIMessage,
    *,
    max_output_tokens: int | None = None,
    session_id: str | None = None,
    model_key: str | None = None,
) -> tuple[TokenUsage, dict[str, Any]]:
    """Extract token usage from LLM response as reported by the provider."""
    raw_usage = _raw_openai_usage(response)
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    if raw_usage:
        provider = _usage_from_raw(raw_usage)
        usage_source = "response_metadata.usage"
    elif usage_metadata:
        provider = _usage_from_metadata(usage_metadata)
        usage_source = "usage_metadata"
    else:
        provider = TokenUsage()
        usage_source = "none"

    diagnostics = _build_usage_diagnostics(
        provider,
        usage_source=usage_source,
        raw_usage=raw_usage,
        usage_metadata=usage_metadata,
        max_output_tokens=max_output_tokens,
    )
    _log_usage_diagnostics(
        provider,
        diagnostics,
        session_id=session_id,
        model_key=model_key,
    )
    return provider, {"usage_diagnostics": diagnostics}


def _extract_model_name(response: AIMessage, model_key: str | None = None) -> str:
    """Extract model name from LLM response."""
    if hasattr(response, "response_metadata") and response.response_metadata:
        # model_name is the key for openai
        model_name = response.response_metadata.get("model_name")
        if model_name:
            return model_name
        model_name = response.response_metadata.get("model")
        if model_name:
            return model_name
        if model_key:
            return model_key
    return "unknown"


# ============ Session Lifecycle Tracking ============


async def record_session_start(context: AgentRuntimeContext) -> None:
    """Record session start event.

    Call this at the beginning of agent invocation to mark session start.
    This provides an accurate session start timestamp.

    Args:
        context: Agent runtime context with user, agent, session info

    Example:
        runtime = extract_runtime_context(config)
        await record_session_start(runtime)
        result = await agent.ainvoke(initial_state, config)
    """
    try:
        metrics_context = _extract_metrics_context(context)

        event = MetricsEvent(
            event_type=EventType.SESSION_START,
            start_time=_naive_utc_now(),
            end_time=_naive_utc_now(),
            context=metrics_context,
            status=CallStatus.SUCCESS,
        )

        await get_metrics_storage().save_event(event)
        logger.debug(f"Recorded SESSION_START for session {metrics_context.session_id}")
    except Exception as e:
        logger.warning(f"Failed to record session start: {e}", exc_info=True)


async def record_session_end(context: AgentRuntimeContext) -> None:
    """Record session end event.

    Call this after agent invocation completes to mark session end.
    This provides an accurate session end timestamp and marks session as completed.

    Args:
        context: Agent runtime context with user, agent, session info

    Example:
        result = await agent.ainvoke(initial_state, config)
        runtime = extract_runtime_context(config)
        await record_session_end(runtime)
    """
    try:
        metrics_context = _extract_metrics_context(context)

        event = MetricsEvent(
            event_type=EventType.SESSION_END,
            context=metrics_context,
            start_time=_naive_utc_now(),
            end_time=_naive_utc_now(),
            status=CallStatus.SUCCESS,
        )

        await get_metrics_storage().save_event(event)
        logger.debug(f"Recorded SESSION_END for session {metrics_context.session_id}")
    except Exception as e:
        logger.warning(f"Failed to record session end: {e}", exc_info=True)


@asynccontextmanager
async def session_tracker(context: AgentRuntimeContext):
    """Context manager for tracking complete session lifecycle.

    Automatically records session start and end events, ensuring proper cleanup
    even when exceptions occur. Preferred over manual record_session_start/end calls.

    Args:
        context: Agent runtime context with user, agent, session info

    Usage:
        runtime = extract_runtime_context(config)
        async with session_tracker(runtime):
            result = await agent.ainvoke(initial_state, config)
            # ... process result ...
        # SESSION_END automatically recorded here
    """
    await record_session_start(context)
    try:
        yield context
    finally:
        await record_session_end(context)


__all__ = [
    "llm_call_tracker",
    "tool_call_tracker",
    "session_tracker",
    "record_session_start",
    "record_session_end",
    "get_metrics_storage",
]
