"""General-purpose agent metrics collection system (V3).

This version addresses key limitations of V2:
1. Real-time persistence - metrics saved immediately after each call
2. Context decoupling - RuntimeContext passed explicitly for type safety
3. Independent querying - metrics stored separately, queryable anytime
4. Pluggable storage - Memory or Database backend, easy to switch

Architecture:
    Context Manager → Emitter → Storage (Memory/DB) → Query

Design principles:
- Events are immutable and context-complete
- Storage is asynchronous and non-blocking
- Failures in metrics don't affect agent execution
- Context is passed explicitly as AgentRuntimeContext

Usage:
    # Use context managers (recommended)
    from apps.tenant_app_service.agents.metrics import llm_call_tracker
    from apps.tenant_app_service.agents.context import extract_runtime_context

    class AgentBase:
        async def _llm_call(self, state, config):
            runtime = extract_runtime_context(config)
            async with llm_call_tracker(model_key, runtime) as tracker:
                response = await model.ainvoke(...)
                tracker.record_response(response)
            return {"messages": [response]}

    # Query metrics using ObservabilityService
    from apps.shared.observability.service import ObservabilityService
    obs_service = ObservabilityService.create(db, tenant_id)
    metrics = await obs_service.get_session_metrics(session_id)

Note: This file re-exports domain models for backward compatibility.
Core implementations are in agent_metrics_instrumentation.py and shared.observability.
"""

# Re-export domain models from shared.observability (backward compatibility)
from apps.shared.observability import (
    CallStatus,
    EventType,
    MetricsContext,
    MetricsEvent,
    SessionMetrics,
    TokenUsage,
)

__all__ = [
    "CallStatus",
    "EventType",
    "MetricsContext",
    "TokenUsage",
    "MetricsEvent",
    "SessionMetrics",
]
