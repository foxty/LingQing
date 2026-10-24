"""Repository for thread_main_messages (human + promoted AI)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ThreadMainMessage
from apps.tenant_app_service.chat.agent_run_domain import ThreadMainMessageDomain


def _to_domain(row: ThreadMainMessage) -> ThreadMainMessageDomain:
    return ThreadMainMessageDomain(
        id=row.id,
        message_id=row.message_id,
        thread_id=row.thread_id,
        type=row.type,
        content=row.content,
        timestamp=row.timestamp,
        agent_id=row.agent_id,
        trigger_message_id=row.trigger_message_id,
        agent_run_id=row.agent_run_id,
        invoke_index=row.invoke_index,
        session_id=row.session_id,
        additional_kwargs=row.additional_kwargs,
        message_metadata=row.message_metadata,
        created_at=row.created_at,
    )


class MainMessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def insert_human(
        self,
        *,
        message_id: str,
        thread_id: str,
        content: str,
        timestamp: datetime | None = None,
        message_metadata: dict | None = None,
        additional_kwargs: dict | None = None,
    ) -> ThreadMainMessageDomain:
        ts = timestamp or datetime.now(UTC)
        row = ThreadMainMessage(
            message_id=message_id,
            thread_id=thread_id,
            type="human",
            content=content,
            timestamp=ts,
            message_metadata=message_metadata,
            additional_kwargs=additional_kwargs,
        )
        self.db.add(row)
        await self.db.flush()
        return _to_domain(row)

    async def get_by_message_id(self, thread_id: str, message_id: str) -> ThreadMainMessageDomain | None:
        result = await self.db.execute(
            select(ThreadMainMessage).where(
                ThreadMainMessage.thread_id == thread_id,
                ThreadMainMessage.message_id == message_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def get_promoted_ai_for_run(self, agent_run_id: str) -> ThreadMainMessageDomain | None:
        result = await self.db.execute(
            select(ThreadMainMessage).where(ThreadMainMessage.agent_run_id == agent_run_id)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def insert_promoted_ai(
        self,
        *,
        message_id: str,
        thread_id: str,
        content: str,
        agent_id: int,
        trigger_message_id: str,
        agent_run_id: str,
        invoke_index: int,
        session_id: str,
        timestamp: datetime | None = None,
        message_metadata: dict | None = None,
        additional_kwargs: dict | None = None,
    ) -> ThreadMainMessageDomain:
        ts = timestamp or datetime.now(UTC)
        row = ThreadMainMessage(
            message_id=message_id,
            thread_id=thread_id,
            type="ai",
            content=content,
            agent_id=agent_id,
            trigger_message_id=trigger_message_id,
            agent_run_id=agent_run_id,
            invoke_index=invoke_index,
            session_id=session_id,
            timestamp=ts,
            message_metadata=message_metadata,
            additional_kwargs=additional_kwargs,
        )
        self.db.add(row)
        await self.db.flush()
        return _to_domain(row)

    async def get_latest_human(self, thread_id: str) -> ThreadMainMessageDomain | None:
        result = await self.db.execute(
            select(ThreadMainMessage)
            .where(ThreadMainMessage.thread_id == thread_id, ThreadMainMessage.type == "human")
            .order_by(ThreadMainMessage.created_at.desc(), ThreadMainMessage.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def has_promoted_ai_for_session(self, thread_id: str, session_id: str) -> bool:
        result = await self.db.execute(
            select(ThreadMainMessage.id)
            .where(
                ThreadMainMessage.thread_id == thread_id,
                ThreadMainMessage.type == "ai",
                ThreadMainMessage.session_id == session_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_latest_promoted_ai_for_session(
        self, thread_id: str, session_id: str
    ) -> ThreadMainMessageDomain | None:
        result = await self.db.execute(
            select(ThreadMainMessage)
            .where(
                ThreadMainMessage.thread_id == thread_id,
                ThreadMainMessage.session_id == session_id,
                ThreadMainMessage.type == "ai",
            )
            .order_by(ThreadMainMessage.created_at.desc(), ThreadMainMessage.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def get_by_message_id_only(self, message_id: str) -> ThreadMainMessage | None:
        result = await self.db.execute(
            select(ThreadMainMessage).where(ThreadMainMessage.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def update_message_metadata(self, row: ThreadMainMessage, metadata: dict) -> None:
        row.message_metadata = metadata
        await self.db.flush()

    async def list_for_thread(self, thread_id: str) -> list[ThreadMainMessageDomain]:
        result = await self.db.execute(
            select(ThreadMainMessage)
            .where(ThreadMainMessage.thread_id == thread_id)
            .order_by(ThreadMainMessage.created_at.asc(), ThreadMainMessage.id.asc())
        )
        return [_to_domain(row) for row in result.scalars().all()]
