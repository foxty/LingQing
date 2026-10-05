"""Service layer for message feedback."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.tenant_app_service.chat.service import ChatService
from apps.tenant_app_service.message_feedback.domain import (
    FEEDBACK_RATING_NEGATIVE,
    FEEDBACK_RATING_POSITIVE,
    FEEDBACK_SOURCE_PORTAL,
    FeedbackRating,
    FeedbackSource,
    MessageFeedbackDomain,
    truncate_preview,
)
from apps.tenant_app_service.message_feedback.repository import MessageFeedbackRepository, feedback_row_to_domain
from apps.tenant_app_service.message_feedback.schemas import (
    FeedbackAgentStats,
    FeedbackListItem,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatsResponse,
    ThreadFeedbackMapResponse,
)


def _to_response(domain: MessageFeedbackDomain) -> FeedbackResponse:
    return FeedbackResponse(
        message_id=domain.message_id,
        rating=domain.rating,
        comment=domain.comment,
        source=domain.source,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
    )


class MessageFeedbackService:
    """Business logic for collecting and analyzing message feedback."""

    def __init__(self, tenant_id: int, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self.repository = MessageFeedbackRepository(db)
        self.chat_service = ChatService(tenant_id, db)

    async def _ensure_thread_access(self, thread_id: str, user_id: int) -> None:
        thread = await self.chat_service.get_thread(thread_id)
        if not thread:
            raise ResourceNotFoundError(f"Thread {thread_id} not found")
        if thread.user_id != user_id:
            raise AuthorizationError("Access denied")

    async def _resolve_ai_message(self, thread_id: str, message_id: str):
        ai_message = await self.repository.get_ai_message(self.tenant_id, message_id)
        if not ai_message or ai_message.thread_id != thread_id:
            raise ResourceNotFoundError(f"Message {message_id} not found in thread")
        return ai_message

    async def _resolve_agent_id(self, thread_id: str, message_agent_id: int | None) -> int:
        if message_agent_id is not None:
            return message_agent_id
        thread = await self.chat_service.get_thread(thread_id)
        if thread is None or thread.agent_id is None:
            raise ValidationError("Unable to resolve agent for feedback")
        return thread.agent_id

    async def _upsert_for_ai_message(
        self,
        ai_message,
        *,
        user_id: int,
        rating: FeedbackRating,
        comment: str | None = None,
        source: FeedbackSource = FEEDBACK_SOURCE_PORTAL,
        external_ref: dict | None = None,
    ) -> FeedbackResponse:
        await self._ensure_thread_access(ai_message.thread_id, user_id)
        agent_id = await self._resolve_agent_id(ai_message.thread_id, ai_message.agent_id)
        now = datetime.now(UTC)
        domain = await self.repository.upsert(
            tenant_id=self.tenant_id,
            thread_id=ai_message.thread_id,
            session_id=ai_message.session_id,
            message_id=ai_message.message_id,
            agent_id=agent_id,
            user_id=user_id,
            rating=rating,
            comment=comment.strip() if comment else None,
            source=source,
            external_ref=external_ref,
            now=now,
        )
        await self.db.commit()
        return _to_response(domain)

    async def upsert_feedback(
        self,
        *,
        thread_id: str,
        message_id: str,
        user_id: int,
        rating: FeedbackRating,
        comment: str | None = None,
        source: FeedbackSource = FEEDBACK_SOURCE_PORTAL,
        external_ref: dict | None = None,
    ) -> FeedbackResponse:
        if rating not in {FEEDBACK_RATING_POSITIVE, FEEDBACK_RATING_NEGATIVE}:
            raise ValidationError("Invalid rating")

        ai_message = await self._resolve_ai_message(thread_id, message_id)
        return await self._upsert_for_ai_message(
            ai_message,
            user_id=user_id,
            rating=rating,
            comment=comment,
            source=source,
            external_ref=external_ref,
        )

    async def upsert_feedback_for_message_id(
        self,
        *,
        message_id: str,
        user_id: int,
        rating: FeedbackRating,
        comment: str | None = None,
        source: FeedbackSource = FEEDBACK_SOURCE_PORTAL,
        external_ref: dict | None = None,
    ) -> FeedbackResponse:
        if rating not in {FEEDBACK_RATING_POSITIVE, FEEDBACK_RATING_NEGATIVE}:
            raise ValidationError("Invalid rating")

        ai_message = await self.repository.get_ai_message(self.tenant_id, message_id)
        if not ai_message:
            raise ResourceNotFoundError(f"Message {message_id} not found")
        return await self._upsert_for_ai_message(
            ai_message,
            user_id=user_id,
            rating=rating,
            comment=comment,
            source=source,
            external_ref=external_ref,
        )

    async def delete_feedback(
        self,
        *,
        thread_id: str,
        message_id: str,
        user_id: int,
    ) -> None:
        await self._ensure_thread_access(thread_id, user_id)
        await self._resolve_ai_message(thread_id, message_id)
        deleted = await self.repository.delete(self.tenant_id, message_id, user_id)
        if not deleted:
            raise ResourceNotFoundError("Feedback not found")
        await self.db.commit()

    async def get_thread_feedback_map(
        self,
        *,
        thread_id: str,
        user_id: int,
    ) -> ThreadFeedbackMapResponse:
        await self._ensure_thread_access(thread_id, user_id)
        rows = await self.repository.list_for_thread(self.tenant_id, thread_id)
        feedback_map = {
            row.message_id: _to_response(feedback_row_to_domain(row))
            for row in rows
            if row.user_id == user_id
        }
        return ThreadFeedbackMapResponse(thread_id=thread_id, feedback=feedback_map)

    async def update_comment(
        self,
        *,
        message_id: str,
        user_id: int,
        comment: str | None,
    ) -> FeedbackResponse | None:
        existing_row = await self.repository.get_by_user_and_message(
            self.tenant_id,
            message_id,
            user_id,
        )
        if existing_row is None:
            return None
        await self._ensure_thread_access(existing_row.thread_id, user_id)

        now = datetime.now(UTC)
        domain = await self.repository.update_comment(
            self.tenant_id,
            message_id,
            user_id,
            comment.strip() if comment else None,
            now,
        )
        if domain is None:
            return None
        await self.db.commit()
        return _to_response(domain)

    async def get_stats(
        self,
        *,
        agent_id: int | None = None,
        source: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> FeedbackStatsResponse:
        positive, negative, by_agent = await self.repository.aggregate_stats(
            self.tenant_id,
            agent_id=agent_id,
            source=source,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        total = positive + negative
        rate = (positive / total) if total else 0.0
        return FeedbackStatsResponse(
            positive_count=positive,
            negative_count=negative,
            total_count=total,
            positive_rate=round(rate, 4),
            by_agent=[
                FeedbackAgentStats(
                    agent_id=agent_id_val,
                    positive_count=pos,
                    negative_count=neg,
                    total_count=pos + neg,
                )
                for agent_id_val, pos, neg in by_agent
            ],
        )

    async def list_feedback(
        self,
        *,
        agent_id: int | None = None,
        rating: str | None = None,
        source: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        cursor: int | None = None,
        limit: int = 50,
    ) -> FeedbackListResponse:
        rows, has_more = await self.repository.list_paginated(
            self.tenant_id,
            agent_id=agent_id,
            rating=rating,
            source=source,
            from_dt=from_dt,
            to_dt=to_dt,
            cursor=cursor,
            limit=limit,
        )
        message_ids = [row.message_id for row, _ in rows]
        session_keys = [(row.thread_id, row.session_id) for row, _ in rows]
        ai_by_id = await self.repository.get_ai_messages_by_ids(self.tenant_id, message_ids)
        human_previews = await self.repository.get_human_previews_for_sessions(session_keys)

        items: list[FeedbackListItem] = []
        for row, username in rows:
            ai_message = ai_by_id.get(row.message_id)
            human_preview = (
                human_previews.get((row.thread_id, row.session_id)) if row.session_id else None
            )
            items.append(
                FeedbackListItem(
                    id=row.id,
                    thread_id=row.thread_id,
                    session_id=row.session_id,
                    message_id=row.message_id,
                    agent_id=row.agent_id,
                    user_id=row.user_id,
                    username=username,
                    rating=row.rating,  # type: ignore[arg-type]
                    comment=row.comment,
                    source=row.source,  # type: ignore[arg-type]
                    human_message_preview=human_preview,
                    ai_message_preview=truncate_preview(ai_message.content if ai_message else None),
                    created_at=row.created_at,
                )
            )
        next_cursor = items[-1].id if items and has_more else None
        return FeedbackListResponse(items=items, next_cursor=next_cursor, has_more=has_more)

    async def export_feedback_csv(
        self,
        *,
        agent_id: int | None = None,
        rating: str | None = None,
        source: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> str:
        all_items: list[FeedbackListItem] = []
        cursor: int | None = None
        while True:
            page = await self.list_feedback(
                agent_id=agent_id,
                rating=rating,
                source=source,
                from_dt=from_dt,
                to_dt=to_dt,
                cursor=cursor,
                limit=200,
            )
            all_items.extend(page.items)
            if not page.has_more or page.next_cursor is None:
                break
            cursor = page.next_cursor

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "thread_id",
                "session_id",
                "message_id",
                "agent_id",
                "user_id",
                "username",
                "rating",
                "comment",
                "source",
                "human_message_preview",
                "ai_message_preview",
                "created_at",
            ]
        )
        for item in all_items:
            writer.writerow(
                [
                    item.id,
                    item.thread_id,
                    item.session_id or "",
                    item.message_id,
                    item.agent_id,
                    item.user_id,
                    item.username or "",
                    item.rating,
                    item.comment or "",
                    item.source,
                    item.human_message_preview or "",
                    item.ai_message_preview or "",
                    item.created_at.isoformat(),
                ]
            )
        return buffer.getvalue()

    async def resolve_message_context(
        self,
        message_id: str,
    ) -> tuple[str, int, str | None, int]:
        """Resolve thread_id, agent_id, session_id for a message (Slack interactivity)."""
        ai_message = await self.repository.get_ai_message(self.tenant_id, message_id)
        if not ai_message:
            raise ResourceNotFoundError(f"Message {message_id} not found")
        agent_id = await self._resolve_agent_id(ai_message.thread_id, ai_message.agent_id)
        return (
            ai_message.thread_id,
            agent_id,
            ai_message.session_id,
            ai_message.id,
        )
