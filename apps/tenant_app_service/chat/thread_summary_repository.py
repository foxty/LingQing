"""Thread summary repository for chat module."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ThreadSummary
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class ThreadSummaryRepository:
    """Repository for thread summary operations."""

    def __init__(self, db: AsyncSession):
        """Initialize repository.

        Args:
            db: Database session
        """
        self.db = db

    async def create(self, thread_summary: ThreadSummary) -> ThreadSummary:
        """Create a new thread summary.

        Args:
            thread_summary: ThreadSummary model to create

        Returns:
            Created ThreadSummary with ID populated
        """
        self.db.add(thread_summary)
        await self.db.flush()
        logger.debug(f"Created thread summary v{thread_summary.version} for thread {thread_summary.thread_id}")
        return thread_summary

    async def get_latest_version(self, thread_id: str) -> int:
        """Get the latest version number for a thread.

        Args:
            thread_id: Thread ID

        Returns:
            Latest version number, or 0 if no summaries exist
        """
        from sqlalchemy import func

        stmt = select(func.max(ThreadSummary.version)).where(ThreadSummary.thread_id == thread_id)
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()
        return version if version is not None else 0

    async def get_recent_summaries(
        self,
        thread_id: str,
        limit: int = 3,
    ) -> list[ThreadSummary]:
        """Get recent thread summaries.

        Args:
            thread_id: Thread ID
            limit: Maximum number of summaries to return (most recent)

        Returns:
            List of ThreadSummary ordered by version DESC
        """
        stmt = (
            select(ThreadSummary)
            .where(ThreadSummary.thread_id == thread_id)
            .order_by(ThreadSummary.version.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        summaries = list(result.scalars().all())
        logger.debug(f"Fetched {len(summaries)} recent thread summaries for thread {thread_id}")
        return summaries

    async def get_all_summaries(self, thread_id: str) -> list[ThreadSummary]:
        """Get all thread summaries for a thread.

        Args:
            thread_id: Thread ID

        Returns:
            List of ThreadSummary ordered by version DESC
        """
        stmt = select(ThreadSummary).where(ThreadSummary.thread_id == thread_id).order_by(ThreadSummary.version.desc())
        result = await self.db.execute(stmt)
        summaries = list(result.scalars().all())
        logger.debug(f"Fetched all {len(summaries)} thread summaries for thread {thread_id}")
        return summaries

    async def get_by_version(self, thread_id: str, version: int) -> ThreadSummary | None:
        """Get a specific version of thread summary.

        Args:
            thread_id: Thread ID
            version: Summary version

        Returns:
            ThreadSummary or None if not found
        """
        stmt = select(ThreadSummary).where(
            ThreadSummary.thread_id == thread_id,
            ThreadSummary.version == version,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_summaries(self, thread_id: str) -> int:
        """Count thread summaries for a thread.

        Args:
            thread_id: Thread ID

        Returns:
            Count of thread summaries
        """
        from sqlalchemy import func

        stmt = select(func.count(ThreadSummary.id)).where(ThreadSummary.thread_id == thread_id)
        result = await self.db.execute(stmt)
        count = result.scalar_one()
        return count
