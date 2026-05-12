"""Domain models for agent observability.

Migrated from chat_backend/agents/metrics/agent_metrics_v3.py

Domain models are framework-agnostic and represent pure business entities.
They use dataclasses and should not depend on Pydantic, SQLAlchemy, or any external frameworks.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from apps.shared.domain.base_domain_model import BaseDomainModel
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


# ============ Constants ============


class CallStatus:
    """Execution status constants."""

    SUCCESS = "success"
    ERROR = "error"


def format_model_label(model_key: str | None, model_name: str | None) -> str | None:
    """Build a consistent model label when request and response model ids differ."""
    if model_key and model_name and model_key != model_name:
        return f"{model_key} → {model_name}"
    return model_key or model_name


class EventType:
    """Metrics event type constants.

    Events represent completed outcomes and lifecycle markers.
    Each event is self-contained with all necessary metrics.
    Use the 'status' field to distinguish success/error outcomes.
    """

    # Session lifecycle events
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Operation events (status field indicates success/error)
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"


# ============ Context Models ============


@dataclass
class MetricsContext(BaseDomainModel):
    """Complete context for metrics events.

    Combines execution context (tenant, user, agent) and call context (configuration).
    All fields are optional to handle missing context gracefully.
    """

    # ===== Execution Context (from RuntimeContext) =====

    # Session identifiers
    session_id: str
    thread_id: str | None = None

    # Tenant/User/Agent context
    tenant_id: int | None = None
    tenant_name: str | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    user_id: int | None = None
    username: str | None = None

    # ===== Call Context (configuration & relationships) =====

    # LLM configuration
    model_key: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    message_count: int | None = None
    message_id: str | None = None  # From LLM call response
    has_tool_calls: bool | None = None

    # Tool configuration
    tool_name: str | None = None
    tool_call_id: str | None = None  # From tool call execution

    # Message identifiers (for tracing LLM/Tool calls)

    @classmethod
    def from_runnable_config(cls, config: RunnableConfig, session_id: str | None = None) -> "MetricsContext":
        """Extract metrics context from RunnableConfig.

        This automatically pulls RuntimeContext if available, or creates
        a minimal context if not.

        Args:
            config: LangGraph RunnableConfig
            session_id: Optional session ID override (uses RuntimeContext.session_id if available)

        Returns:
            MetricsContext with all available information
        """
        # Extract configurable section
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")

        # Try to extract RuntimeContext
        runtime = configurable.get("runtime", {})

        # Prioritize session_id from RuntimeContext, then fallback to parameter or generate
        runtime_session_id = runtime.get("session_id")
        if not session_id:
            session_id = runtime_session_id or str(uuid4())

        # Extract user context
        user_ctx = runtime.get("user", {})
        user_id = user_ctx.get("user_id")
        username = user_ctx.get("username")
        user_tenant_id = user_ctx.get("tenant_id")
        user_tenant_name = user_ctx.get("tenant_name")

        # Extract agent context
        agent_ctx = runtime.get("agent", {})
        agent_id = agent_ctx.get("agent_id")
        agent_name = agent_ctx.get("agent_name")
        agent_tenant_id = agent_ctx.get("tenant_id")
        agent_tenant_name = agent_ctx.get("tenant_name")

        # Prefer agent context for tenant (more stable)
        tenant_id = agent_tenant_id or user_tenant_id
        tenant_name = agent_tenant_name or user_tenant_name

        return cls(
            session_id=session_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            agent_id=agent_id,
            agent_name=agent_name,
            user_id=user_id,
            username=username,
        )


# ============ Event Models ============


@dataclass
class TokenUsage(BaseDomainModel):
    """Token usage for a single call."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class MetricsEvent(BaseDomainModel):
    """Base event model for all metrics events.

    Stores raw naive UTC datetimes to align with DB columns
    defined as TIMESTAMP WITHOUT TIME ZONE.
    """

    # Event metadata
    event_type: str
    context: MetricsContext
    start_time: datetime  # Call start time (naive UTC)
    end_time: datetime  # Call end time (naive UTC)
    # Optional fields with defaults
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    status: str = CallStatus.SUCCESS
    error_message: str | None = None
    token_usage: TokenUsage | None = None
    input_size: int | None = None
    output_size: int | None = None
    duration_ms: float | None = None  # Calculated from end_time - start_time

    # Extra context (optional large-capacity data)
    # Stored separately for selective querying to avoid performance issues
    # Potential keys:
    # - tool_input_preview: str (configurable length)
    # - tool_output_preview: str (configurable length)
    # - tool_input_size: int (original size)
    # - tool_output_size: int (original size)
    # - tool_calls: list[dict] (for LLM responses with tool calls)
    extra_context: dict[str, Any] = field(default_factory=dict)


# Type aliases for specific event types (for clarity in code)
LLMCallEvent = MetricsEvent
ToolCallEvent = MetricsEvent


# ============ Aggregated Metrics (calculated from events) ============


@dataclass
class AgentSessionMetrics(BaseDomainModel):
    """Aggregated metrics for a single session, calculated from raw events.

    A session represents a single agent execution and contains multiple events.
    All calculation logic resides in this domain model.
    """

    # Session identifiers
    session_id: str
    thread_id: str | None = None

    # Context
    tenant_id: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    user_id: int | None = None
    username: str | None = None

    # Timing
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: float | None = None

    # Aggregated counts
    llm_call_count: int = 0
    tool_call_count: int = 0
    error_count: int = 0
    total_event_count: int = 0

    # Token usage
    total_tokens: TokenUsage = field(default_factory=TokenUsage)

    # Per-model breakdown
    model_usage: dict[str, dict[str, int]] = field(default_factory=dict)

    # Per-tool breakdown
    tool_usage: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Status
    status: str = "active"

    @classmethod
    def from_events(cls, events: list[MetricsEvent]) -> "AgentSessionMetrics":
        """Calculate session metrics from a list of raw events.

        Args:
            events: List of MetricsEvent for a single session

        Returns:
            AgentSessionMetrics with calculated aggregations

        Raises:
            ValueError: If events list is empty or contains multiple sessions
        """
        if not events:
            raise ValueError("Cannot calculate metrics from empty event list")

        # Validate all events belong to same session
        session_ids = {e.context.session_id for e in events}
        if len(session_ids) > 1:
            raise ValueError(f"Events must belong to same session, got: {session_ids}")

        # Extract session context from first event
        first_event = events[0]
        session_id = first_event.context.session_id
        thread_id = first_event.context.thread_id
        tenant_id = first_event.context.tenant_id
        agent_id = first_event.context.agent_id
        agent_name = first_event.context.agent_name
        user_id = first_event.context.user_id
        username = first_event.context.username

        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # Calculate timing
        start_dt = sorted_events[0].timestamp
        end_dt = sorted_events[-1].timestamp
        duration_ms = (end_dt - start_dt).total_seconds() * 1000
        # Keep session metrics times as ISO strings for API compatibility
        start_time = start_dt.isoformat()
        end_time = end_dt.isoformat()

        # Calculate counts
        llm_call_count = sum(1 for e in events if e.event_type == EventType.LLM_CALL)
        tool_call_count = sum(1 for e in events if e.event_type == EventType.TOOL_CALL)
        error_count = sum(1 for e in events if e.status == CallStatus.ERROR)

        # Calculate token usage
        total_input_tokens = 0
        total_output_tokens = 0
        for event in events:
            if event.token_usage:
                total_input_tokens += event.token_usage.input_tokens
                total_output_tokens += event.token_usage.output_tokens

        total_tokens = TokenUsage(
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_tokens=total_input_tokens + total_output_tokens,
        )

        # Calculate per-model usage
        model_usage: dict[str, dict[str, int]] = {}
        for event in events:
            model_name = format_model_label(event.context.model_key, event.context.model_name)
            if model_name and event.token_usage:
                if model_name not in model_usage:
                    model_usage[model_name] = {"calls": 0, "tokens": 0}
                model_usage[model_name]["calls"] += 1
                model_usage[model_name]["tokens"] += event.token_usage.total_tokens

        # Calculate per-tool usage
        tool_usage: dict[str, dict[str, Any]] = {}
        for event in events:
            if event.context.tool_name:
                tool_name = event.context.tool_name
                if tool_name not in tool_usage:
                    tool_usage[tool_name] = {
                        "calls": 0,
                        "errors": 0,
                        "total_duration_ms": 0.0,
                        "avg_duration_ms": 0.0,
                    }
                tool_usage[tool_name]["calls"] += 1
                if event.status == CallStatus.ERROR:
                    tool_usage[tool_name]["errors"] += 1
                if event.duration_ms:
                    tool_usage[tool_name]["total_duration_ms"] += event.duration_ms

        # Calculate average durations for tools
        for tool_name, usage in tool_usage.items():
            if usage["calls"] > 0:
                usage["avg_duration_ms"] = usage["total_duration_ms"] / usage["calls"]

        # Determine session status
        has_session_end = any(e.event_type == EventType.SESSION_END for e in events)
        has_errors = error_count > 0
        if has_session_end:
            status = "error" if has_errors else "completed"
        else:
            status = "active"

        return cls(
            session_id=session_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_name=agent_name,
            user_id=user_id,
            username=username,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            llm_call_count=llm_call_count,
            tool_call_count=tool_call_count,
            error_count=error_count,
            total_event_count=len(events),
            total_tokens=total_tokens,
            model_usage=model_usage,
            tool_usage=tool_usage,
            status=status,
        )


@dataclass
class AgentThreadMetrics(BaseDomainModel):
    """Aggregated metrics for a thread, calculated from session metrics.

    A thread represents a conversation and contains multiple sessions.
    All calculation logic resides in this domain model.
    """

    # Thread identifiers
    thread_id: str
    tenant_id: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None

    # Timing (across all sessions)
    first_session_start: str | None = None
    last_session_end: str | None = None
    total_duration_ms: float = 0.0

    # Session-level aggregations
    session_count: int = 0
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_errors: int = 0
    total_events: int = 0

    # Token usage (across all sessions)
    total_tokens: TokenUsage = field(default_factory=TokenUsage)

    # Per-model breakdown (across all sessions)
    model_usage: dict[str, dict[str, int]] = field(default_factory=dict)

    # Per-tool breakdown (across all sessions)
    tool_usage: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Session details
    sessions: list[AgentSessionMetrics] = field(default_factory=list)

    @classmethod
    def from_sessions(cls, sessions: list[AgentSessionMetrics]) -> "AgentThreadMetrics":
        """Calculate thread metrics from a list of session metrics.

        Args:
            sessions: List of AgentSessionMetrics for a single thread

        Returns:
            AgentThreadMetrics with calculated aggregations

        Raises:
            ValueError: If sessions list is empty or contains multiple threads
        """
        if not sessions:
            raise ValueError("Cannot calculate thread metrics from empty session list")

        # Validate all sessions belong to same thread
        thread_ids = {s.thread_id for s in sessions if s.thread_id}
        if len(thread_ids) > 1:
            raise ValueError(f"Sessions must belong to same thread, got: {thread_ids}")
        if not thread_ids:
            raise ValueError("Sessions must have thread_id set")

        thread_id = thread_ids.pop()

        # Extract thread context from first session
        first_session = sessions[0]
        tenant_id = first_session.tenant_id
        agent_id = first_session.agent_id
        agent_name = first_session.agent_name

        # Sort sessions by start time (start_time/end_time are ISO strings)
        sorted_sessions = sorted(
            [s for s in sessions if s.start_time],
            key=lambda s: s.start_time,  # ISO string comparison works correctly
        )

        # Calculate timing
        first_session_start = sorted_sessions[0].start_time if sorted_sessions else None
        last_session_end = max(
            (s.end_time for s in sessions if s.end_time),
            default=None,
        )  # ISO strings sort lexicographically

        total_duration_ms = sum(s.duration_ms or 0.0 for s in sessions)

        # Aggregate counts
        session_count = len(sessions)
        total_llm_calls = sum(s.llm_call_count for s in sessions)
        total_tool_calls = sum(s.tool_call_count for s in sessions)
        total_errors = sum(s.error_count for s in sessions)
        total_events = sum(s.total_event_count for s in sessions)

        # Aggregate token usage
        total_input_tokens = sum(s.total_tokens.input_tokens for s in sessions)
        total_output_tokens = sum(s.total_tokens.output_tokens for s in sessions)
        total_tokens = TokenUsage(
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_tokens=total_input_tokens + total_output_tokens,
        )

        # Aggregate per-model usage
        model_usage: dict[str, dict[str, int]] = {}
        for session in sessions:
            for model_key, usage in session.model_usage.items():
                if model_key not in model_usage:
                    model_usage[model_key] = {"calls": 0, "tokens": 0}
                model_usage[model_key]["calls"] += usage["calls"]
                model_usage[model_key]["tokens"] += usage["tokens"]

        # Aggregate per-tool usage
        tool_usage_aggregator: dict[str, dict[str, Any]] = {}
        for session in sessions:
            for tool_name, usage in session.tool_usage.items():
                if tool_name not in tool_usage_aggregator:
                    tool_usage_aggregator[tool_name] = {
                        "calls": 0,
                        "errors": 0,
                        "total_duration_ms": 0.0,
                    }
                tool_usage_aggregator[tool_name]["calls"] += usage["calls"]
                tool_usage_aggregator[tool_name]["errors"] += usage["errors"]
                # Use total_duration_ms from session if available, else calculate from avg
                if "total_duration_ms" in usage:
                    tool_usage_aggregator[tool_name]["total_duration_ms"] += usage["total_duration_ms"]
                else:
                    tool_usage_aggregator[tool_name]["total_duration_ms"] += usage["avg_duration_ms"] * usage["calls"]

        # Calculate average durations for tools
        tool_usage: dict[str, dict[str, Any]] = {}
        for tool_name, agg in tool_usage_aggregator.items():
            tool_usage[tool_name] = {
                "calls": agg["calls"],
                "errors": agg["errors"],
                "avg_duration_ms": (agg["total_duration_ms"] / agg["calls"] if agg["calls"] > 0 else 0.0),
            }

        return cls(
            thread_id=thread_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_name=agent_name,
            first_session_start=first_session_start,
            last_session_end=last_session_end,
            total_duration_ms=total_duration_ms,
            session_count=session_count,
            total_llm_calls=total_llm_calls,
            total_tool_calls=total_tool_calls,
            total_errors=total_errors,
            total_events=total_events,
            total_tokens=total_tokens,
            model_usage=model_usage,
            tool_usage=tool_usage,
            sessions=sessions,
        )


# Legacy alias for backward compatibility
SessionMetrics = AgentSessionMetrics
