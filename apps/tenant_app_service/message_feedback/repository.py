"""Repository for message feedback."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatMessage, ChatThread, MessageFeedback, User
from apps.tenant_app_service.message_feedback.domain import MessageFeedbackDomain, truncate_preview


def feedback_row_to_domain(row: MessageFeedback) -> MessageFeedbackDomain:
    return MessageFeedbackDomain(
        id=row.id,
        tenant_id=row.tenant_id,
        thread_id=row.thread_id,
        session_id=row.session_id,
        message_id=row.message_id,
        agent_id=row.agent_id,
        user_id=row.user_id,
        rating=row.rating,  # type: ignore[arg-type]
        comment=row.comment,
        source=row.source,  # type: ignore[arg-type]
        external_ref=row.external_ref,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class MessageFeedbackRepository:
    """Tenant-scoped persistence for message feedback."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_user_and_message(
        self,
        tenant_id: int,
        message_id: str,
        user_id: int,
    ) -> MessageFeedback | None:
        result = await self.db.execute(
            select(MessageFeedback).where(
                MessageFeedback.tenant_id == tenant_id,
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_thread(self, tenant_id: int, thread_id: str) -> list[MessageFeedback]:
        result = await self.db.execute(
            select(MessageFeedback)
            .where(
                MessageFeedback.tenant_id == tenant_id,
                MessageFeedback.thread_id == thread_id,
            )
            .order_by(MessageFeedback.created_at.asc())
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        session_id: str | None,
        message_id: str,
        agent_id: int,
        user_id: int,
        rating: str,
        comment: str | None,
        source: str,
        external_ref: dict | None,
        now: datetime,
    ) -> MessageFeedbackDomain:
        existing = await self.get_by_user_and_message(tenant_id, message_id, user_id)
        if existing:
            existing.rating = rating
            existing.comment = comment
            existing.source = source
            existing.external_ref = external_ref
            existing.updated_at = now
            await self.db.flush()
            return feedback_row_to_domain(existing)

        row = MessageFeedback(
            tenant_id=tenant_id,
            thread_id=thread_id,
            session_id=session_id,
            message_id=message_id,
            agent_id=agent_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
            source=source,
            external_ref=external_ref,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        await self.db.flush()
        return feedback_row_to_domain(row)

    async def delete(
        self,
        tenant_id: int,
        message_id: str,
        user_id: int,
    ) -> bool:
        existing = await self.get_by_user_and_message(tenant_id, message_id, user_id)
        if not existing:
            return False
        await self.db.delete(existing)
        await self.db.flush()
        return True

    async def update_comment(
        self,
        tenant_id: int,
        message_id: str,
        user_id: int,
        comment: str | None,
        now: datetime,
    ) -> MessageFeedbackDomain | None:
        existing = await self.get_by_user_and_message(tenant_id, message_id, user_id)
        if not existing:
            return None
        existing.comment = comment
        existing.updated_at = now
        await self.db.flush()
        return feedback_row_to_domain(existing)

    async def aggregate_stats(
        self,
        tenant_id: int,
        *,
        agent_id: int | None = None,
        source: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> tuple[int, int, list[tuple[int, int, int]]]:
        filters = [MessageFeedback.tenant_id == tenant_id]
        if agent_id is not None:
            filters.append(MessageFeedback.agent_id == agent_id)
        if source is not None:
            filters.append(MessageFeedback.source == source)
        if from_dt is not None:
            filters.append(MessageFeedback.created_at >= from_dt)
        if to_dt is not None:
            filters.append(MessageFeedback.created_at <= to_dt)

        positive = func.sum(case((MessageFeedback.rating == "positive", 1), else_=0))
        negative = func.sum(case((MessageFeedback.rating == "negative", 1), else_=0))

        overall = await self.db.execute(
            select(
                func.coalesce(positive, 0),
                func.coalesce(negative, 0),
            ).where(and_(*filters))
        )
        pos_total, neg_total = overall.one()

        by_agent_result = await self.db.execute(
            select(
                MessageFeedback.agent_id,
                func.coalesce(positive, 0),
                func.coalesce(negative, 0),
            )
            .where(and_(*filters))
            .group_by(MessageFeedback.agent_id)
            .order_by(MessageFeedback.agent_id.asc())
        )
        by_agent = [(int(r[0]), int(r[1]), int(r[2])) for r in by_agent_result.all()]
        return int(pos_total), int(neg_total), by_agent

    async def list_paginated(
        self,
        tenant_id: int,
        *,
        agent_id: int | None = None,
        rating: str | None = None,
        source: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        cursor: int | None = None,
        limit: int = 50,
    ) -> tuple[list[tuple[MessageFeedback, str | None]], bool]:
        filters = [MessageFeedback.tenant_id == tenant_id]
        if agent_id is not None:
            filters.append(MessageFeedback.agent_id == agent_id)
        if rating is not None:
            filters.append(MessageFeedback.rating == rating)
        if source is not None:
            filters.append(MessageFeedback.source == source)
        if from_dt is not None:
            filters.append(MessageFeedback.created_at >= from_dt)
        if to_dt is not None:
            filters.append(MessageFeedback.created_at <= to_dt)
        if cursor is not None:
            filters.append(MessageFeedback.id < cursor)

        query = (
            select(MessageFeedback, User.username)
            .outerjoin(
                User,
                and_(User.id == MessageFeedback.user_id, User.tenant_id == MessageFeedback.tenant_id),
            )
            .where(and_(*filters))
            .order_by(MessageFeedback.id.desc())
            .limit(limit + 1)
        )
        result = await self.db.execute(query)
        rows = list(result.all())
        has_more = len(rows) > limit
        page = rows[:limit]
        return page, has_more

    async def get_ai_message(self, tenant_id: int, message_id: str) -> ChatMessage | None:
        by_id = await self.get_ai_messages_by_ids(tenant_id, [message_id])
        return by_id.get(message_id)

    async def get_ai_messages_by_ids(
        self,
        tenant_id: int,
        message_ids: list[str],
    ) -> dict[str, ChatMessage]:
        if not message_ids:
            return {}
        unique_ids = list(dict.fromkeys(message_ids))
        result = await self.db.execute(
            select(ChatMessage)
            .join(ChatThread, ChatMessage.thread_id == ChatThread.id)
            .where(
                ChatMessage.message_id.in_(unique_ids),
                ChatMessage.type == "ai",
                ChatThread.tenant_id == tenant_id,
            )
        )
        return {
            message.message_id: message
            for message in result.scalars().all()
            if message.message_id is not None
        }

    async def get_human_previews_for_sessions(
        self,
        session_keys: list[tuple[str, str | None]],
        *,
        max_len: int = 200,
    ) -> dict[tuple[str, str], str | None]:
        pairs = {(thread_id, session_id) for thread_id, session_id in session_keys if session_id}
        if not pairs:
            return {}

        thread_ids = {thread_id for thread_id, _ in pairs}
        session_ids = {session_id for _, session_id in pairs}
        result = await self.db.execute(
            select(
                ChatMessage.thread_id,
                ChatMessage.session_id,
                ChatMessage.content,
            )
            .where(
                ChatMessage.thread_id.in_(thread_ids),
                ChatMessage.session_id.in_(session_ids),
                ChatMessage.type == "human",
            )
            .order_by(ChatMessage.created_at.asc())
        )
        previews: dict[tuple[str, str], str | None] = {}
        for thread_id, session_id, content in result.all():
            if session_id is None:
                continue
            key = (thread_id, session_id)
            if key in pairs and key not in previews:
                previews[key] = truncate_preview(content, max_len=max_len)
        return previews

    async def get_human_preview_for_session(
        self,
        thread_id: str,
        session_id: str | None,
        *,
        max_len: int = 200,
    ) -> str | None:
        if not session_id:
            return None
        result = await self.db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.session_id == session_id,
                ChatMessage.type == "human",
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        content = result.scalar_one_or_none()
        return truncate_preview(content, max_len=max_len)
