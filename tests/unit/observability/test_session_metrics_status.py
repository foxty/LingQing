"""Session status aggregation (RFC Phase 1)."""

from datetime import UTC, datetime

from apps.shared.observability.domain import CallStatus, EventType, MetricsContext, MetricsEvent, AgentSessionMetrics


def _session_events(*, with_end: bool, tool_error: bool) -> list[MetricsEvent]:
    now = datetime.now(UTC)
    ctx = MetricsContext(session_id="s-phase1")
    events = [
        MetricsEvent(event_type=EventType.SESSION_START, context=ctx, start_time=now, end_time=now),
        MetricsEvent(event_type=EventType.LLM_CALL, context=ctx, start_time=now, end_time=now),
    ]
    if tool_error:
        events.append(
            MetricsEvent(
                event_type=EventType.TOOL_CALL,
                status=CallStatus.ERROR,
                context=ctx,
                start_time=now,
                end_time=now,
            )
        )
    if with_end:
        events.append(MetricsEvent(event_type=EventType.SESSION_END, context=ctx, start_time=now, end_time=now))
    return events


def test_completed_with_tool_errors_when_session_ended():
    metrics = AgentSessionMetrics.from_events(_session_events(with_end=True, tool_error=True))
    assert metrics.status == "completed_with_tool_errors"
    assert metrics.error_count == 1


def test_completed_when_no_errors_and_session_ended():
    metrics = AgentSessionMetrics.from_events(_session_events(with_end=True, tool_error=False))
    assert metrics.status == "completed"


def test_active_when_session_not_ended():
    metrics = AgentSessionMetrics.from_events(_session_events(with_end=False, tool_error=True))
    assert metrics.status == "active"