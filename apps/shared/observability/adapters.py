"""Adapters for converting between domain and database models."""

from dataclasses import asdict

from apps.shared.db.models import AgentMetricsEventDBModel
from apps.shared.observability.domain import MetricsContext, MetricsEvent, TokenUsage


def event_to_db_model(event: MetricsEvent) -> AgentMetricsEventDBModel:
    """Convert domain MetricsEvent to database model.

    Args:
        event: Domain event

    Returns:
        Database model ready for persistence
    """
    return AgentMetricsEventDBModel(
        event_id=event.event_id,
        event_type=event.event_type,
        status=event.status,
        timestamp=event.timestamp,
        start_time=event.start_time,
        end_time=event.end_time,
        session_id=event.context.session_id,
        thread_id=event.context.thread_id,
        tenant_id=event.context.tenant_id,
        agent_id=event.context.agent_id,
        user_id=event.context.user_id,
        context=asdict(event.context),
        extra_context=event.extra_context if event.extra_context else None,
        input_tokens=event.token_usage.input_tokens if event.token_usage else None,
        output_tokens=event.token_usage.output_tokens if event.token_usage else None,
        total_tokens=event.token_usage.total_tokens if event.token_usage else None,
        duration_ms=event.duration_ms,
        input_size=event.input_size,
        output_size=event.output_size,
        error_message=event.error_message,
    )


def db_model_to_event(db_model: AgentMetricsEventDBModel) -> MetricsEvent:
    """Convert database model to domain MetricsEvent.

    Args:
        db_model: Database model

    Returns:
        Domain event
    """
    context = MetricsContext(**db_model.context)

    # Reconstruct token usage if available
    token_usage = None
    if db_model.total_tokens is not None:
        token_usage = TokenUsage(
            input_tokens=db_model.input_tokens or 0,
            output_tokens=db_model.output_tokens or 0,
            total_tokens=db_model.total_tokens,
        )

    return MetricsEvent(
        event_id=db_model.event_id,
        event_type=db_model.event_type,
        status=db_model.status,
        timestamp=db_model.timestamp,
        start_time=db_model.start_time if db_model.start_time else db_model.timestamp,
        end_time=db_model.end_time if db_model.end_time else db_model.timestamp,
        context=context,
        error_message=db_model.error_message,
        token_usage=token_usage,
        input_size=db_model.input_size,
        output_size=db_model.output_size,
        duration_ms=db_model.duration_ms,
        extra_context=db_model.extra_context or {},
    )
