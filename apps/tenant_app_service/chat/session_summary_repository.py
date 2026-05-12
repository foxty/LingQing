"""Session summary repository for chat module."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import SessionSummary
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class SessionSummaryRepository:
    """Repository for session summary operations."""

    def __init__(self, db: AsyncSession):
        """Initialize repository.

        Args:
            db: Database session
        """
        self.db = db

    async def create(self, session_summary: SessionSummary) -> SessionSummary:
        """Create a new session summary.

        Args:
            session_summary: SessionSummary model to create

        Returns:
            Created SessionSummary with ID populated
        """
        self.db.add(session_summary)
        await self.db.flush()
        logger.debug(f"Created session summary {session_summary.session_id}")
        return session_summary

    async def get_by_session_id(self, session_id: str) -> SessionSummary | None:
        """Get session summary by session ID.

        Args:
            session_id: Session ID

        Returns:
            SessionSummary or None if not found
        """
        stmt = select(SessionSummary).where(SessionSummary.session_id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_summaries(
        self,
        thread_id: str,
        limit: int = 10,
    ) -> list[SessionSummary]:
        """Get recent session summaries for a thread.

        Args:
            thread_id: Thread ID
            limit: Maximum number of summaries to return (most recent)

        Returns:
            List of SessionSummary ordered by created_at DESC
        """
        stmt = (
            select(SessionSummary)
            .where(SessionSummary.thread_id == thread_id)
            .order_by(SessionSummary.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        summaries = list(result.scalars().all())
        logger.debug(f"Fetched {len(summaries)} recent session summaries for thread {thread_id}")
        return summaries

    async def get_unsummarized_sessions(
        self,
        thread_id: str,
    ) -> list[SessionSummary]:
        """Get sessions that haven't been included in a thread summary.

        Args:
            thread_id: Thread ID

        Returns:
            List of SessionSummary not yet included in thread summary, ordered by created_at ASC
        """
        stmt = (
            select(SessionSummary)
            .where(
                SessionSummary.thread_id == thread_id,
                SessionSummary.included_in_thread_summary == False,  # noqa: E712
            )
            .order_by(SessionSummary.created_at.asc())
        )
        result = await self.db.execute(stmt)
        summaries = list(result.scalars().all())
        logger.debug(f"Found {len(summaries)} unsummarized sessions for thread {thread_id}")
        return summaries

    async def count_unsummarized_sessions(self, thread_id: str) -> int:
        """Count sessions not yet included in a thread summary.

        Args:
            thread_id: Thread ID

        Returns:
            Count of unsummarized sessions
        """
        from sqlalchemy import func

        stmt = select(func.count(SessionSummary.id)).where(
            SessionSummary.thread_id == thread_id,
            SessionSummary.included_in_thread_summary == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        count = result.scalar_one()
        return count

    async def mark_sessions_as_summarized(
        self,
        session_ids: list[str],
        thread_summary_version: int,
    ) -> None:
        """Mark sessions as included in a thread summary.

        Args:
            session_ids: List of session IDs to mark
            thread_summary_version: Version of the thread summary that includes these sessions
        """
        if not session_ids:
            return

        from sqlalchemy import update

        stmt = (
            update(SessionSummary)
            .where(SessionSummary.session_id.in_(session_ids))
            .values(
                included_in_thread_summary=True,
                thread_summary_version=thread_summary_version,
            )
        )
        await self.db.execute(stmt)
        logger.debug(
            f"Marked {len(session_ids)} sessions as summarized (thread summary version {thread_summary_version})"
        )
