"""Thread repository for chat module."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import ChatThread
from apps.tenant_app_service.chat.domain import ThreadDomain


def db_thread_to_domain(db_thread: ChatThread) -> ThreadDomain:
    """Convert database ChatThread to domain model."""
    return ThreadDomain(
        id=db_thread.id,
        tenant_id=db_thread.tenant_id,
        user_id=db_thread.user_id,
        agent_id=db_thread.agent_id,
        title=db_thread.title,
        message_count=db_thread.message_count,
        created_at=db_thread.created_at,
        updated_at=db_thread.updated_at,
    )


class ThreadRepository(BaseRepository[ChatThread]):
    """Repository for thread operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(ChatThread, db)

    async def get_by_id(self, thread_id: str) -> ThreadDomain | None:
        """Get thread by ID."""
        result = await self.db.execute(select(ChatThread).where(ChatThread.id == thread_id))
        db_thread = result.scalar_one_or_none()
        return db_thread_to_domain(db_thread) if db_thread else None

    async def list_by_user(
        self, tenant_id: int, user_id: int, limit: int = 20, agent_id: int | None = None
    ) -> list[ThreadDomain]:
        """List threads for a user, ordered by updated_at desc.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            limit: Maximum number of threads to return
            agent_id: Optional agent ID to filter threads by specific agent
        """
        query = select(ChatThread).where(ChatThread.tenant_id == tenant_id, ChatThread.user_id == user_id)

        if agent_id is not None:
            query = query.where(ChatThread.agent_id == agent_id)

        query = query.order_by(ChatThread.updated_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return [db_thread_to_domain(t) for t in result.scalars().all()]

    async def count_by_user(self, tenant_id: int, user_id: int) -> int:
        """Count threads for a user."""
        result = await self.db.execute(
            select(ChatThread).where(ChatThread.tenant_id == tenant_id, ChatThread.user_id == user_id)
        )
        return len(result.scalars().all())

    async def create_thread(
        self,
        thread_id: str,
        tenant_id: int,
        user_id: int,
        agent_id: int,
        title: str | None = None,
    ) -> ThreadDomain:
        """Create a new thread."""
        thread = ChatThread(
            id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            title=title,
            message_count=0,
        )
        db_thread = await self.create(thread)
        return db_thread_to_domain(db_thread)

    async def update_thread(
        self,
        thread_id: str,
        title: str | None = None,
        message_count: int | None = None,
    ) -> ThreadDomain | None:
        """Update thread metadata."""
        db_thread = await self.get_by_id_raw(thread_id)
        if not db_thread:
            return None

        if title is not None:
            db_thread.title = title
        if message_count is not None:
            db_thread.message_count = message_count

        await self.db.commit()
        await self.db.refresh(db_thread)
        return db_thread_to_domain(db_thread)

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread."""
        result = await self.db.execute(delete(ChatThread).where(ChatThread.id == thread_id))
        await self.db.commit()
        return result.rowcount > 0

    async def delete_oldest_thread(self, tenant_id: int, user_id: int) -> bool:
        """Delete the oldest thread (by updated_at) for a user."""
        result = await self.db.execute(
            select(ChatThread)
            .where(ChatThread.tenant_id == tenant_id, ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.asc())
            .limit(1)
        )
        oldest = result.scalar_one_or_none()
        if oldest:
            return await self.delete_thread(oldest.id)
        return False

    async def get_by_id_raw(self, thread_id: str) -> ChatThread | None:
        """Get raw database ChatThread object."""
        result = await self.db.execute(select(ChatThread).where(ChatThread.id == thread_id))
        return result.scalar_one_or_none()
