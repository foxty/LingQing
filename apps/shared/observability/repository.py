"""Repository for agent metrics data access (CRUD only)."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentMetricsEventDBModel
from apps.shared.observability.adapters import db_model_to_event, event_to_db_model
from apps.shared.observability.domain import MetricsEvent
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
