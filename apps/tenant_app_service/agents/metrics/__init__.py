"""Agent metrics collection system.

This module provides metrics collection for agent execution:
- V3 (agent_metrics_v3*.py): Event-based metrics with storage backends
- Instrumentation: Decorator-based collection (agent_metrics_instrumentation.py)
"""

# Instrumentation exports
# V3 exports (re-export from shared.observability)
from apps.shared.observability import (
    CallStatus,
    EventType,
    MetricsContext,
    MetricsEvent,
    SessionMetrics,
)
from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import (
    get_metrics_storage,
    llm_call_tracker,
    record_session_end,
    record_session_start,
    session_tracker,
    tool_call_tracker,
)
from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import (
    DatabaseStorage,
    MemoryStorage,
    MetricsStorage,
    get_storage,
)

# Type aliases for backward compatibility
LLMCallEvent = MetricsEvent
ToolCallEvent = MetricsEvent

__all__ = [
    # V3 models
    "CallStatus",
    "EventType",
    "LLMCallEvent",
    "MetricsContext",
    "MetricsEvent",
    "SessionMetrics",
    "ToolCallEvent",
    # V3 storage
    "DatabaseStorage",
    "MemoryStorage",
    "MetricsStorage",
    "get_storage",
    # Instrumentation
    "tool_call_tracker",
    "llm_call_tracker",
    "session_tracker",
    "get_metrics_storage",
    "record_session_start",
    "record_session_end",
]
