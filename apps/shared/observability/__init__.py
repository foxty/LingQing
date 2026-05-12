"""Agent observability module - metrics collection, storage, and analysis.

This module provides comprehensive observability for agent execution:
- Metrics collection and storage (events, sessions, threads)
- Usage statistics and analytics
- Foundation for billing and cost tracking

Public exports:
    Domain models: MetricsEvent, AgentSessionMetrics, AgentThreadMetrics, MetricsContext, TokenUsage
    Constants: EventType, CallStatus
    Service: ObservabilityService
    Legacy alias: SessionMetrics (alias for AgentSessionMetrics)
"""

from apps.shared.observability.domain import (
    AgentSessionMetrics,
    AgentThreadMetrics,
    CallStatus,
    EventType,
    MetricsContext,
    MetricsEvent,
    SessionMetrics,
    TokenUsage,
)
from apps.shared.observability.service import ObservabilityService

__all__ = [
    # Domain models
    "MetricsEvent",
    "AgentSessionMetrics",
    "AgentThreadMetrics",
    "MetricsContext",
    "TokenUsage",
    # Legacy alias
    "SessionMetrics",
    # Constants
    "EventType",
    "CallStatus",
    # Service
    "ObservabilityService",
]
