"""Service layer for agent observability - business logic and analytics."""

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.observability.domain import (
    AgentSessionMetrics,
    AgentThreadMetrics,
    CallStatus,
    EventType,
    MetricsEvent,
    SessionMetrics,
    format_model_label,
)
from apps.shared.observability.dtos import TenantUsageStatsDTO
from apps.shared.observability.repository import MetricsRepository
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class ObservabilityService:
    """Business logic for agent observability.

    Provides:
    - Session metrics aggregation
    - Tenant usage statistics
    - Foundation for billing and cost tracking
    """

    def __init__(self, repo: MetricsRepository):
        """Initialize service.

        Args:
            repo: Metrics repository
        """
        self.repo = repo

    @classmethod
    def create(cls, db: AsyncSession, tenant_id: int) -> "ObservabilityService":
        """Create service with dependencies.

        Args:
            db: Database session
            tenant_id: Optional tenant ID for automatic scoping

        Returns:
            ObservabilityService instance
        """
        repo = MetricsRepository(db, tenant_id)
        return cls(repo)

    # ============ Session Metrics ============

    async def get_session_metrics(self, session_id: str) -> SessionMetrics | None:
        """Get aggregated metrics for a session.

        Args:
            session_id: Session ID

        Returns:
            Aggregated metrics or None if session not found
        """
        events = await self.repo.get_events_by_session(session_id)
        if not events:
            return None

        # Use domain model to calculate metrics (business logic in domain layer)
        return AgentSessionMetrics.from_events(events)

    async def get_thread_metrics(self, thread_id: str, limit: int | None = None) -> AgentThreadMetrics | None:
        """Get aggregated metrics for a thread.

        Args:
            thread_id: Thread ID
            limit: Optional max number of sessions to include (None = all sessions)

        Returns:
            AgentThreadMetrics with all sessions aggregated, or None if thread not found
        """
        events = await self.repo.get_events_by_thread(thread_id, limit=None)
        if not events:
            return None

        # Group events by session_id
        sessions: dict[str, list[MetricsEvent]] = defaultdict(list)
        for event in events:
            sessions[event.context.session_id].append(event)

        # Use domain model to calculate metrics for each session
        session_metrics_list: list[AgentSessionMetrics] = []
        for session_id, session_events in sessions.items():
            try:
                metrics = AgentSessionMetrics.from_events(session_events)
                session_metrics_list.append(metrics)
            except ValueError as e:
                logger.warning(f"Failed to calculate metrics for session {session_id}: {e}")
                continue

        if not session_metrics_list:
            return None

        # Sort sessions by start time descending
        session_metrics_list.sort(
            key=lambda m: m.start_time or "",
            reverse=True,
        )

        # Apply limit if specified
        if limit:
            session_metrics_list = session_metrics_list[:limit]

        # Use domain model to aggregate all sessions into thread metrics
        return AgentThreadMetrics.from_sessions(session_metrics_list)

    # ============ Tenant Usage Statistics ============

    async def get_tenant_usage_stats(
        self,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        user_id: int | None = None,
        agent_id: int | None = None,
    ) -> TenantUsageStatsDTO:
        """Get tenant usage statistics for observability and billing.

        Args:
            tenant_id: Tenant ID
            start_time: Start of period
            end_time: End of period

        Returns:
            Usage statistics DTO
        """
        events = await self.repo.get_events_by_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            agent_id=agent_id,
        )

        # Aggregate statistics
        llm_calls = [e for e in events if e.event_type == EventType.LLM_CALL]
        llm_errors = [e for e in llm_calls if e.status == CallStatus.ERROR]
        tool_calls = [e for e in events if e.event_type == EventType.TOOL_CALL]
        tool_errors = [e for e in tool_calls if e.status == CallStatus.ERROR]

        # Token usage
        total_input_tokens = sum(e.token_usage.input_tokens for e in llm_calls if e.token_usage)
        total_output_tokens = sum(e.token_usage.output_tokens for e in llm_calls if e.token_usage)
        total_tokens = total_input_tokens + total_output_tokens

        # Unique counts
        unique_sessions = len(set(e.context.session_id for e in events))
        unique_threads = len(set(e.context.thread_id for e in events if e.context.thread_id is not None))
        unique_users = len(set(e.context.user_id for e in events if e.context.user_id is not None))

        return TenantUsageStatsDTO(
            tenant_id=tenant_id,
            period_start=start_time,
            period_end=end_time,
            total_llm_calls=len(llm_calls),
            total_llm_errors=len(llm_errors),
            total_tool_calls=len(tool_calls),
            total_tool_errors=len(tool_errors),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_tokens=total_tokens,
            unique_sessions=unique_sessions,
            unique_threads=unique_threads,
            unique_users=unique_users,
            estimated_cost=None,  # Future: implement cost calculation
        )

    async def get_tenant_token_daily_usage(
        self,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        user_id: int | None = None,
        agent_id: int | None = None,
    ) -> list[dict]:
        """Get daily token usage trend for a tenant.

        Args:
            tenant_id: Tenant ID
            start_time: Start of period
            end_time: End of period

        Returns:
            List of daily usage dictionaries ordered by date ascending
        """
        events = await self.repo.get_events_by_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            event_types=[EventType.LLM_CALL],
            user_id=user_id,
            agent_id=agent_id,
            limit=50000,
        )

        daily: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "llm_calls": 0,
                "llm_errors": 0,
            }
        )

        for event in events:
            timestamp = event.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            date_key = timestamp.astimezone(UTC).date().isoformat()

            daily_entry = daily[date_key]
            daily_entry["llm_calls"] += 1
            if event.status == "error":
                daily_entry["llm_errors"] += 1

            if event.token_usage:
                daily_entry["total_input_tokens"] += event.token_usage.input_tokens
                daily_entry["total_output_tokens"] += event.token_usage.output_tokens
                daily_entry["total_tokens"] += (
                    event.token_usage.input_tokens + event.token_usage.output_tokens
                )

        return [
            {
                "date": date,
                "total_input_tokens": values["total_input_tokens"],
                "total_output_tokens": values["total_output_tokens"],
                "total_tokens": values["total_tokens"],
                "llm_calls": values["llm_calls"],
                "llm_errors": values["llm_errors"],
            }
            for date, values in sorted(daily.items(), key=lambda item: item[0])
        ]

    async def get_tenant_token_events(
        self,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
        agent_id: int | None = None,
    ) -> tuple[int, list[dict]]:
        """Get paginated token consumption events for a tenant.

        Args:
            tenant_id: Tenant ID
            start_time: Start of period
            end_time: End of period
            page: Page number (1-based)
            page_size: Page size
            user_id: Optional user filter
            agent_id: Optional agent filter

        Returns:
            Tuple of (total_count, rows)
        """
        offset = (page - 1) * page_size

        total = await self.repo.count_events_by_filters(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            event_types=[EventType.LLM_CALL],
        )

        events = await self.repo.get_events_page_by_filters(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            event_types=[EventType.LLM_CALL],
            offset=offset,
            limit=page_size,
        )

        rows = []
        for event in events:
            rows.append(
                {
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                    "session_id": event.context.session_id,
                    "thread_id": event.context.thread_id,
                    "user_id": event.context.user_id,
                    "username": event.context.username,
                    "agent_id": event.context.agent_id,
                    "agent_name": event.context.agent_name,
                    "model_key": event.context.model_key,
                    "model_name": event.context.model_name,
                    "model_label": event.extra_context.get("model_label")
                    or format_model_label(event.context.model_key, event.context.model_name),
                    "input_tokens": event.token_usage.input_tokens if event.token_usage else 0,
                    "output_tokens": event.token_usage.output_tokens if event.token_usage else 0,
                    "total_tokens": event.token_usage.total_tokens if event.token_usage else 0,
                    "duration_ms": event.duration_ms,
                    "status": event.status,
                }
            )

        return total, rows

    async def delete_session_events(self, session_id: str) -> int:
        """Delete all events for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of events deleted
        """
        return await self.repo.delete_events_by_session(session_id)

    # ============ Tool Call Metrics ============

    async def get_session_tool_calls(self, session_id: str) -> list[dict]:
        """Get all tool call events for a session.

        Args:
            session_id: Session ID

        Returns:
            List of tool call metrics dictionaries
        """
        events = await self.repo.get_events_by_session(session_id)
        tool_events = [e for e in events if e.event_type == EventType.TOOL_CALL]

        return [
            {
                "tool_call_id": e.context.tool_call_id,
                "tool_name": e.context.tool_name,
                "status": e.status,
                "duration_ms": e.duration_ms,
                "input_size": e.input_size,
                "output_size": e.output_size,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "error_message": e.error_message,
            }
            for e in tool_events
        ]

    async def get_tool_call_metrics(self, session_id: str, tool_call_id: str) -> dict | None:
        """Get metrics for a specific tool call.

        Args:
            session_id: Session ID
            tool_call_id: Tool call ID

        Returns:
            Tool call metrics dictionary or None if not found
        """
        events = await self.repo.get_events_by_session(session_id)
        tool_event = next(
            (e for e in events if e.event_type == EventType.TOOL_CALL and e.context.tool_call_id == tool_call_id),
            None,
        )

        if not tool_event:
            return None

        return {
            "tool_call_id": tool_event.context.tool_call_id,
            "tool_name": tool_event.context.tool_name,
            "status": tool_event.status,
            "duration_ms": tool_event.duration_ms,
            "input_size": tool_event.input_size,
            "output_size": tool_event.output_size,
            "start_time": tool_event.start_time,
            "end_time": tool_event.end_time,
            "error_message": tool_event.error_message,
            "extra_context": tool_event.extra_context,
        }
