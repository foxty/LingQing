"""Storage backends for agent metrics V3.

Provides pluggable storage implementations:
- MemoryStorage: Fast, in-memory storage for testing/development
- DatabaseStorage: Persistent DB storage for production

Design:
- Abstract interface for storage operations
- Async operations for non-blocking
- Error isolation (metrics failures don't break agent execution)
- Queryable by session_id, thread_id, tenant_id
"""

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime

from apps.shared.db.session import app_db_session
from apps.shared.observability import EventType, MetricsEvent, SessionMetrics
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


# ============ Abstract Storage Interface ============


class MetricsStorage(ABC):
    """Abstract interface for metrics storage.

    Storage layer only handles event persistence.
    Query/aggregation logic lives in ObservabilityService.
    """

    @abstractmethod
    async def save_event(self, event: MetricsEvent) -> None:
        """Save metrics event.

        Args:
            event: Metrics event to save
        """
        pass


# ============ Memory Storage Implementation ============


class MemoryStorage(MetricsStorage):
    """In-memory storage for metrics events.

    Fast and simple, suitable for:
    - Development and testing
    - Single-instance deployments
    - Short-lived sessions

    Limitations:
    - Data lost on restart
    - No cross-process sharing
    - Memory grows unbounded (use cleanup)
    """

    def __init__(self):
        """Initialize memory storage."""
        # Store all events by session_id
        self._events: dict[str, list[MetricsEvent]] = defaultdict(list)

        # Index for quick thread_id lookup
        self._session_to_thread: dict[str, str] = {}

        # Lock for thread-safe access
        self._lock = asyncio.Lock()

        logger.info("Initialized MemoryStorage for metrics")

    async def save_event(self, event: MetricsEvent) -> None:
        """Save metrics event to memory."""
        try:
            async with self._lock:
                session_id = event.context.session_id
                self._events[session_id].append(event)

                # Update thread index
                if event.context.thread_id:
                    self._session_to_thread[session_id] = event.context.thread_id

            logger.debug(f"Saved event: {event.event_type} for session {event.context.session_id}")
        except Exception as e:
            logger.error(f"Failed to save event: {e}", exc_info=True)

    # ============ Query Methods (for backward compatibility) ============
    # Note: These should eventually be replaced by ObservabilityService calls

    async def get_session_metrics(self, session_id: str) -> SessionMetrics | None:
        """Compute aggregated metrics from stored events."""
        try:
            async with self._lock:
                events = self._events.get(session_id, [])

                if not events:
                    return None

                # Get context from first event
                context = events[0].context

                # Initialize metrics
                metrics = SessionMetrics(
                    session_id=session_id,
                    thread_id=context.thread_id,
                    tenant_id=context.user.tenant_id,
                    agent_id=context.agent_id,
                    user_id=context.user.user_id,
                )

                # Separate events by type
                llm_events = [e for e in events if e.event_type in (EventType.LLM_CALL, EventType.LLM_ERROR)]
                tool_events = [e for e in events if e.event_type in (EventType.TOOL_CALL, EventType.TOOL_ERROR)]

                # Aggregate LLM calls - each event is self-contained
                for event in llm_events:
                    if event.event_type == EventType.LLM_CALL:
                        metrics.llm_call_count += 1

                        # Token usage
                        if event.token_usage:
                            metrics.total_tokens.input_tokens += event.token_usage.input_tokens
                            metrics.total_tokens.output_tokens += event.token_usage.output_tokens
                            metrics.total_tokens.total_tokens += event.token_usage.total_tokens

                        # Per-model stats
                        model_key = event.context.model_key or "unknown"
                        if model_key not in metrics.model_usage:
                            metrics.model_usage[model_key] = {"calls": 0, "tokens": 0}
                        metrics.model_usage[model_key]["calls"] += 1
                        if event.token_usage:
                            metrics.model_usage[model_key]["tokens"] += event.token_usage.total_tokens

                    elif event.event_type == EventType.LLM_ERROR:
                        metrics.error_count += 1

                # Aggregate tool calls - each event is self-contained
                tool_durations: dict[str, list[float]] = defaultdict(list)
                for event in tool_events:
                    tool_name = event.context.tool_name or "unknown"

                    if event.event_type == EventType.TOOL_CALL:
                        metrics.tool_call_count += 1

                        # Per-tool stats
                        if tool_name not in metrics.tool_usage:
                            metrics.tool_usage[tool_name] = {
                                "calls": 0,
                                "errors": 0,
                                "avg_duration_ms": 0.0,
                            }
                        metrics.tool_usage[tool_name]["calls"] += 1

                        # Track duration for averaging
                        if event.duration_ms:
                            tool_durations[tool_name].append(event.duration_ms)

                    elif event.event_type == EventType.TOOL_ERROR:
                        metrics.error_count += 1

                        # Per-tool error stats
                        if tool_name not in metrics.tool_usage:
                            metrics.tool_usage[tool_name] = {
                                "calls": 0,
                                "errors": 0,
                                "avg_duration_ms": 0.0,
                            }
                        metrics.tool_usage[tool_name]["errors"] += 1

                # Calculate average durations
                for tool_name, durations in tool_durations.items():
                    if durations:
                        avg = sum(durations) / len(durations)
                        metrics.tool_usage[tool_name]["avg_duration_ms"] = avg

                # Calculate session timing from SESSION_START/END events
                # Fall back to first/last operation events if lifecycle events missing
                if events:
                    # Look for SESSION_START and SESSION_END events
                    session_start_event = next((e for e in events if e.event_type == EventType.SESSION_START), None)
                    session_end_event = next(
                        (e for e in reversed(events) if e.event_type == EventType.SESSION_END), None
                    )

                    # Use SESSION_START if available, otherwise first event
                    if session_start_event:
                        metrics.start_time = session_start_event.timestamp
                    else:
                        metrics.start_time = events[0].timestamp

                    # Use SESSION_END if available, otherwise calculate from last event
                    if session_end_event:
                        metrics.end_time = session_end_event.timestamp
                        metrics.status = "completed"
                    else:
                        # No SESSION_END yet, calculate from last operation event
                        last_event = events[-1]
                        try:
                            last_event_start = datetime.fromisoformat(last_event.timestamp.replace("Z", "+00:00"))
                            last_event_duration_seconds = (last_event.duration_ms or 0) / 1000

                            from datetime import timedelta

                            actual_end = last_event_start + timedelta(seconds=last_event_duration_seconds)
                            metrics.end_time = actual_end.isoformat()
                        except Exception as e:
                            logger.warning(f"Failed to calculate end_time: {e}")
                            metrics.end_time = last_event.timestamp

                        # Session still active if no SESSION_END
                        metrics.status = "active"

                    # Calculate total session duration
                    if metrics.start_time and metrics.end_time:
                        try:
                            start = datetime.fromisoformat(metrics.start_time.replace("Z", "+00:00"))
                            end = datetime.fromisoformat(metrics.end_time.replace("Z", "+00:00"))
                            metrics.duration_ms = (end - start).total_seconds() * 1000
                        except Exception as e:
                            logger.warning(f"Failed to calculate duration: {e}")
                            metrics.duration_ms = 0.0

                    # Update status based on errors (only if not already completed by SESSION_END)
                    if metrics.error_count > 0 and metrics.status != "completed":
                        metrics.status = "error"

                return metrics

        except Exception as e:
            logger.error(f"Failed to get session metrics: {e}", exc_info=True)
            return None

    async def get_thread_metrics(self, thread_id: str, limit: int = 10) -> list[SessionMetrics]:
        """Get metrics for all sessions in a thread."""
        try:
            # Find all sessions for this thread (no lock needed for read-only dict access)
            session_ids = [sid for sid, tid in self._session_to_thread.items() if tid == thread_id]

            # Get metrics for each session (get_session_metrics has its own locking)
            metrics_list = []
            for session_id in session_ids:
                metrics = await self.get_session_metrics(session_id)
                if metrics:
                    metrics_list.append(metrics)

            # Sort by start_time (newest first)
            metrics_list.sort(key=lambda m: m.start_time if m.start_time else "", reverse=True)

            return metrics_list[:limit]

        except Exception as e:
            logger.error(f"Failed to get thread metrics: {e}", exc_info=True)
            return []

    async def cleanup_session(self, session_id: str) -> None:
        """Remove session data from memory.

        Note: For production use, call ObservabilityService.delete_session_events() instead.
        """
        try:
            async with self._lock:
                self._events.pop(session_id, None)
                self._session_to_thread.pop(session_id, None)

            logger.info(f"Cleaned up session {session_id} from memory")
        except Exception as e:
            logger.error(f"Failed to cleanup session: {e}", exc_info=True)


# ============ Database Storage Implementation ============


class DatabaseStorage(MetricsStorage):
    """Database storage for metrics events.

    Persistent and scalable, suitable for:
    - Production deployments
    - Multi-instance deployments
    - Long-term metrics analysis and billing

    Note: Query methods delegate to ObservabilityService.
    """

    def __init__(self, get_db_session):
        """Initialize database storage.

        Args:
            get_db_session: Callable that returns AsyncSession context manager
        """
        self.get_db_session = get_db_session
        logger.debug("Initialized DatabaseStorage for metrics")

    async def save_event(self, event: MetricsEvent) -> None:
        """Save event to database (error isolated)."""
        try:
            from apps.shared.observability.repository import MetricsRepository

            async with self.get_db_session() as db:
                repo = MetricsRepository(db, tenant_id=event.context.tenant_id)
                await repo.save_event(event)
                await db.commit()
                logger.debug("Saved event %s to database, context: %s", event.event_id, event.context)
        except Exception as e:
            logger.error(f"Failed to save metrics event to database: {e}", exc_info=True)
            # Error isolation: don't propagate to agent execution

    # ============ Query Methods (backward compatibility) ============
    # Delegate to ObservabilityService for proper layering

    async def get_session_metrics(self, session_id: str) -> SessionMetrics | None:
        """Get session metrics from database."""
        try:
            from apps.shared.observability.service import ObservabilityService

            async with self.get_db_session() as db:
                service = ObservabilityService.create(db)
                return await service.get_session_metrics(session_id)
        except Exception as e:
            logger.error(f"Failed to get session metrics: {e}", exc_info=True)
            return None

    async def get_thread_metrics(self, thread_id: str, limit: int = 10) -> list[SessionMetrics]:
        """Get thread metrics from database."""
        try:
            from apps.shared.observability.service import ObservabilityService

            async with self.get_db_session() as db:
                service = ObservabilityService.create(db)
                return await service.get_thread_metrics(thread_id, limit)
        except Exception as e:
            logger.error(f"Failed to get thread metrics: {e}", exc_info=True)
            return []

    async def cleanup_session(self, session_id: str) -> None:
        """Clean up session from database.

        Note: Delegates to ObservabilityService for proper layering.
        """
        try:
            from apps.shared.observability.service import ObservabilityService

            async with self.get_db_session() as db:
                service = ObservabilityService.create(db)
                deleted_count = await service.delete_session_events(session_id)
                await db.commit()
                logger.info(f"Deleted {deleted_count} events for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup session: {e}", exc_info=True)


# ============ Storage Factory ============

# Global storage instance (singleton per backend type)
_storage_instances: dict[str, MetricsStorage] = {}


def get_storage(backend) -> MetricsStorage:
    """Get storage instance (singleton).

    Args:
        backend: Storage backend type ("memory" or "database")

    Returns:
        MetricsStorage instance
    """
    if backend not in _storage_instances:
        if backend == "memory":
            _storage_instances[backend] = MemoryStorage()
        elif backend == "database":
            _storage_instances[backend] = DatabaseStorage(app_db_session)
        else:
            logger.warning(f"Unknown storage backend: {backend}, using memory")
            _storage_instances[backend] = MemoryStorage()

    return _storage_instances[backend]


__all__ = [
    "MetricsStorage",
    "MemoryStorage",
    "DatabaseStorage",
    "get_storage",
]
