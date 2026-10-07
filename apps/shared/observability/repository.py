"""Repository for agent metrics data access (CRUD only)."""

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentMetricsEventDBModel
from apps.shared.observability.adapters import db_model_to_event, event_to_db_model
from apps.shared.observability.domain import CallStatus, EventType, MetricsEvent
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class MetricsRepository:
    """Pure CRUD for agent metrics (tenant-scoped).

    All queries are automatically scoped to tenant_id if provided.
    """

    def __init__(self, db: AsyncSession, tenant_id: int | None = None):
        """Initialize repository.

        Args:
            db: Database session
            tenant_id: Optional tenant ID for automatic scoping
        """
        self.db = db
        self.tenant_id = tenant_id

    async def save_event(self, event: MetricsEvent) -> None:
        """Save single event to database.

        Args:
            event: Metrics event to save
        """
        db_model = event_to_db_model(event)
        self.db.add(db_model)
        await self.db.flush()
        logger.debug(f"Saved event {event.event_id} for session {event.context.session_id}")

    async def get_events_by_session(self, session_id: str) -> list[MetricsEvent]:
        """Get all events for a session.

        Args:
            session_id: Session ID

        Returns:
            List of events ordered by timestamp
        """
        query = (
            select(AgentMetricsEventDBModel)
            .where(AgentMetricsEventDBModel.session_id == session_id)
            .order_by(AgentMetricsEventDBModel.timestamp)
        )

        if self.tenant_id:
            query = query.where(AgentMetricsEventDBModel.tenant_id == self.tenant_id)

        result = await self.db.execute(query)
        db_models = result.scalars().all()
        return [db_model_to_event(m) for m in db_models]

    async def get_events_by_thread(self, thread_id: str, limit: int = 100) -> list[MetricsEvent]:
        """Get events for all sessions in a thread.

        Args:
            thread_id: Thread ID
            limit: Max events to return

        Returns:
            List of events ordered by timestamp descending
        """
        query = (
            select(AgentMetricsEventDBModel)
            .where(AgentMetricsEventDBModel.thread_id == thread_id)
            .order_by(AgentMetricsEventDBModel.timestamp.desc())
            .limit(limit)
        )

        if self.tenant_id:
            query = query.where(AgentMetricsEventDBModel.tenant_id == self.tenant_id)

        result = await self.db.execute(query)
        db_models = result.scalars().all()
        return [db_model_to_event(m) for m in db_models]

    async def get_events_by_filters(
        self,
        tenant_id: int | None = None,
        agent_id: int | None = None,
        user_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_types: list[str] | None = None,
        limit: int = 1000,
    ) -> list[MetricsEvent]:
        """Get events by filters (for observability queries).

        Args:
            tenant_id: Filter by tenant ID (overrides repository tenant_id)
            agent_id: Filter by agent ID
            user_id: Filter by user ID
            start_time: Filter events after this time
            end_time: Filter events before this time
            event_types: Filter by event types (e.g., ["llm_call", "tool_call"])
            limit: Max events to return

        Returns:
            List of events matching filters
        """
        query = select(AgentMetricsEventDBModel)

        # Apply tenant filter (use parameter or repository default)
        filter_tenant_id = tenant_id or self.tenant_id
        if filter_tenant_id:
            query = query.where(AgentMetricsEventDBModel.tenant_id == filter_tenant_id)

        if agent_id:
            query = query.where(AgentMetricsEventDBModel.agent_id == agent_id)

        if user_id:
            query = query.where(AgentMetricsEventDBModel.user_id == user_id)

        if start_time:
            query = query.where(AgentMetricsEventDBModel.timestamp >= start_time)

        if end_time:
            query = query.where(AgentMetricsEventDBModel.timestamp <= end_time)

        if event_types:
            query = query.where(AgentMetricsEventDBModel.event_type.in_(event_types))

        query = query.order_by(AgentMetricsEventDBModel.timestamp.desc()).limit(limit)

        result = await self.db.execute(query)
        db_models = result.scalars().all()
        return [db_model_to_event(m) for m in db_models]

    @staticmethod
    def _usage_scope_filters(
        *,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        agent_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple:
        filters = [
            AgentMetricsEventDBModel.tenant_id == tenant_id,
            AgentMetricsEventDBModel.timestamp >= start_time,
            AgentMetricsEventDBModel.timestamp <= end_time,
        ]
        if agent_id is not None:
            filters.append(AgentMetricsEventDBModel.agent_id == agent_id)
        if user_id is not None:
            filters.append(AgentMetricsEventDBModel.user_id == user_id)
        return tuple(filters)

    async def aggregate_usage_stats(
        self,
        *,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        agent_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[int, int, int, int, int, int, int, int, int, float | None, float | None]:
        """Aggregate usage counters in SQL (no row limit).

        Returns:
            Tuple of (
                total_llm_calls,
                total_llm_errors,
                total_tool_calls,
                total_tool_errors,
                total_input_tokens,
                total_output_tokens,
                unique_sessions,
                unique_threads,
                unique_users,
                avg_llm_duration_ms,
                avg_tool_duration_ms,
            )
        """
        filters = self._usage_scope_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            agent_id=agent_id,
            user_id=user_id,
        )
        llm_count = case((AgentMetricsEventDBModel.event_type == EventType.LLM_CALL, 1), else_=0)
        llm_error_count = case(
            (
                (AgentMetricsEventDBModel.event_type == EventType.LLM_CALL)
                & (AgentMetricsEventDBModel.status == CallStatus.ERROR),
                1,
            ),
            else_=0,
        )
        tool_count = case((AgentMetricsEventDBModel.event_type == EventType.TOOL_CALL, 1), else_=0)
        tool_error_count = case(
            (
                (AgentMetricsEventDBModel.event_type == EventType.TOOL_CALL)
                & (AgentMetricsEventDBModel.status == CallStatus.ERROR),
                1,
            ),
            else_=0,
        )
        input_tokens = case(
            (
                AgentMetricsEventDBModel.event_type == EventType.LLM_CALL,
                func.coalesce(AgentMetricsEventDBModel.input_tokens, 0),
            ),
            else_=0,
        )
        output_tokens = case(
            (
                AgentMetricsEventDBModel.event_type == EventType.LLM_CALL,
                func.coalesce(AgentMetricsEventDBModel.output_tokens, 0),
            ),
            else_=0,
        )
        avg_llm_duration = func.avg(
            case(
                (AgentMetricsEventDBModel.event_type == EventType.LLM_CALL, AgentMetricsEventDBModel.duration_ms),
            )
        )
        avg_tool_duration = func.avg(
            case(
                (AgentMetricsEventDBModel.event_type == EventType.TOOL_CALL, AgentMetricsEventDBModel.duration_ms),
            )
        )
        query = select(
            func.coalesce(func.sum(llm_count), 0),
            func.coalesce(func.sum(llm_error_count), 0),
            func.coalesce(func.sum(tool_count), 0),
            func.coalesce(func.sum(tool_error_count), 0),
            func.coalesce(func.sum(input_tokens), 0),
            func.coalesce(func.sum(output_tokens), 0),
            func.count(func.distinct(AgentMetricsEventDBModel.session_id)),
            func.count(func.distinct(AgentMetricsEventDBModel.thread_id)),
            func.count(func.distinct(AgentMetricsEventDBModel.user_id)),
            avg_llm_duration,
            avg_tool_duration,
        ).where(*filters)
        result = await self.db.execute(query)
        row = result.one()
        return (
            int(row[0]),
            int(row[1]),
            int(row[2]),
            int(row[3]),
            int(row[4]),
            int(row[5]),
            int(row[6]),
            int(row[7]),
            int(row[8]),
            float(row[9]) if row[9] is not None else None,
            float(row[10]) if row[10] is not None else None,
        )

    async def aggregate_daily_token_usage(
        self,
        *,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        agent_id: int | None = None,
        user_id: int | None = None,
    ) -> list[tuple[datetime, int, int, int, int]]:
        """Aggregate daily LLM token usage in SQL (no row limit).

        Returns:
            List of (day, total_input_tokens, total_output_tokens, llm_calls, llm_errors)
            ordered by day ascending.
        """
        filters = self._usage_scope_filters(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            agent_id=agent_id,
            user_id=user_id,
        ) + (AgentMetricsEventDBModel.event_type == EventType.LLM_CALL,)
        day_bucket = func.date_trunc("day", AgentMetricsEventDBModel.timestamp).label("day")
        llm_error_count = case(
            (AgentMetricsEventDBModel.status == CallStatus.ERROR, 1),
            else_=0,
        )
        query = (
            select(
                day_bucket,
                func.coalesce(func.sum(func.coalesce(AgentMetricsEventDBModel.input_tokens, 0)), 0),
                func.coalesce(func.sum(func.coalesce(AgentMetricsEventDBModel.output_tokens, 0)), 0),
                func.count(),
                func.coalesce(func.sum(llm_error_count), 0),
            )
            .where(*filters)
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
        result = await self.db.execute(query)
        return [
            (
                row.day,
                int(row[1]),
                int(row[2]),
                int(row[3]),
                int(row[4]),
            )
            for row in result.all()
        ]

    async def count_events_by_filters(
        self,
        tenant_id: int | None = None,
        agent_id: int | None = None,
        user_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_types: list[str] | None = None,
    ) -> int:
        """Count events by filters (for paginated queries).

        Args:
            tenant_id: Filter by tenant ID (overrides repository tenant_id)
            agent_id: Filter by agent ID
            user_id: Filter by user ID
            start_time: Filter events after this time
            end_time: Filter events before this time
            event_types: Filter by event types

        Returns:
            Count of events matching filters
        """
        query = select(func.count(AgentMetricsEventDBModel.id))

        filter_tenant_id = tenant_id or self.tenant_id
        if filter_tenant_id:
            query = query.where(AgentMetricsEventDBModel.tenant_id == filter_tenant_id)

        if agent_id:
            query = query.where(AgentMetricsEventDBModel.agent_id == agent_id)

        if user_id:
            query = query.where(AgentMetricsEventDBModel.user_id == user_id)

        if start_time:
            query = query.where(AgentMetricsEventDBModel.timestamp >= start_time)

        if end_time:
            query = query.where(AgentMetricsEventDBModel.timestamp <= end_time)

        if event_types:
            query = query.where(AgentMetricsEventDBModel.event_type.in_(event_types))

        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_events_page_by_filters(
        self,
        tenant_id: int | None = None,
        agent_id: int | None = None,
        user_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_types: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[MetricsEvent]:
        """Get paginated events by filters.

        Args:
            tenant_id: Filter by tenant ID (overrides repository tenant_id)
            agent_id: Filter by agent ID
            user_id: Filter by user ID
            start_time: Filter events after this time
            end_time: Filter events before this time
            event_types: Filter by event types
            offset: Number of rows to skip
            limit: Max events to return

        Returns:
            List of events matching filters (ordered by timestamp desc)
        """
        query = select(AgentMetricsEventDBModel)

        filter_tenant_id = tenant_id or self.tenant_id
        if filter_tenant_id:
            query = query.where(AgentMetricsEventDBModel.tenant_id == filter_tenant_id)

        if agent_id:
            query = query.where(AgentMetricsEventDBModel.agent_id == agent_id)

        if user_id:
            query = query.where(AgentMetricsEventDBModel.user_id == user_id)

        if start_time:
            query = query.where(AgentMetricsEventDBModel.timestamp >= start_time)

        if end_time:
            query = query.where(AgentMetricsEventDBModel.timestamp <= end_time)

        if event_types:
            query = query.where(AgentMetricsEventDBModel.event_type.in_(event_types))

        query = query.order_by(AgentMetricsEventDBModel.timestamp.desc()).offset(offset).limit(limit)

        result = await self.db.execute(query)
        db_models = result.scalars().all()
        return [db_model_to_event(m) for m in db_models]

    async def delete_events_by_session(self, session_id: str) -> int:
        """Delete all events for a session (cleanup).

        Args:
            session_id: Session ID

        Returns:
            Number of deleted events
        """
        query = select(AgentMetricsEventDBModel).where(AgentMetricsEventDBModel.session_id == session_id)

        if self.tenant_id:
            query = query.where(AgentMetricsEventDBModel.tenant_id == self.tenant_id)

        result = await self.db.execute(query)
        events = result.scalars().all()

        for event in events:
            await self.db.delete(event)

        await self.db.flush()
        logger.info(f"Deleted {len(events)} events for session {session_id}")
        return len(events)
