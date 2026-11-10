"""Service layer for message feedback."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.shared.db.session import app_db_session
from apps.shared.utils.structured_export import CsvTableExporter
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.message_feedback.domain import (
    FEEDBACK_RATING_NEGATIVE,
    FEEDBACK_RATING_POSITIVE,
    FEEDBACK_SOURCE_PORTAL,
    FEEDBACK_SOURCE_SLACK,
    FeedbackRating,
    FeedbackSource,
    FeedbackTargetMessage,
    MessageFeedbackDomain,
    normalize_feedback_comment,
    normalize_message_content,
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


def _resolve_human_message(
    *,
    thread_id: str,
    session_id: str | None,
    ai_message: FeedbackTargetMessage | None,
    human_by_trigger: dict[tuple[str, str], str | None],
    human_by_session: dict[tuple[str, str], str | None],
) -> str | None:
    if ai_message and ai_message.trigger_message_id:
        hit = human_by_trigger.get((ai_message.thread_id, ai_message.trigger_message_id))
        if hit:
            return hit
    if session_id:
        return human_by_session.get((thread_id, session_id))
    return None


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
        self.thread_service = ThreadService(tenant_id, db)

    async def _ensure_thread_access(
        self,
        thread_id: str,
        user_id: int,
        *,
        source: FeedbackSource = FEEDBACK_SOURCE_PORTAL,
    ) -> None:
        thread = await self.thread_service.get_thread(thread_id)
        if not thread:
            raise ResourceNotFoundError(f"Thread {thread_id} not found")
        if source != FEEDBACK_SOURCE_SLACK and thread.user_id != user_id:
            raise AuthorizationError("Access denied")

    async def _resolve_ai_message(self, thread_id: str, message_id: str):
        ai_message = await self.repository.get_ai_message(self.tenant_id, message_id)
        if not ai_message or ai_message.thread_id != thread_id:
            raise ResourceNotFoundError(f"Message {message_id} not found in thread")
        return ai_message

    async def _resolve_agent_id(self, thread_id: str, message_agent_id: int | None) -> int:
        if message_agent_id is not None:
            return message_agent_id
        thread = await self.thread_service.get_thread(thread_id)
        if thread is None or thread.agent_id is None:
            raise ValidationError("Unable to resolve agent for feedback")
        return thread.agent_id

    async def _upsert_for_ai_message(
        self,
        ai_message: FeedbackTargetMessage,
        *,
        user_id: int,
        rating: FeedbackRating,
        comment: str | None = None,
        source: FeedbackSource = FEEDBACK_SOURCE_PORTAL,
        external_ref: dict | None = None,
    ) -> FeedbackResponse:
        await self._ensure_thread_access(ai_message.thread_id, user_id, source=source)
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
            comment=normalize_feedback_comment(comment),
            source=source,
            external_ref=external_ref,
            now=now,
        )
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
            normalize_feedback_comment(comment),
            now,
        )
        if domain is None:
            return None
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
        trigger_keys = [
            (ai.thread_id, ai.trigger_message_id)
            for ai in ai_by_id.values()
            if ai.trigger_message_id
        ]
        human_by_trigger = await self.repository.get_human_contents_by_triggers(
            self.tenant_id,
            trigger_keys,
        )
        human_by_session = await self.repository.get_human_previews_for_sessions(session_keys)

        items: list[FeedbackListItem] = []
        for row, username in rows:
            ai_message = ai_by_id.get(row.message_id)
            human_preview = _resolve_human_message(
                thread_id=row.thread_id,
                session_id=row.session_id,
                ai_message=ai_message,
                human_by_trigger=human_by_trigger,
                human_by_session=human_by_session,
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

    async def _append_feedback_export_page(
        self,
        exporter: CsvTableExporter,
        *,
        agent_id: int | None,
        rating: str | None,
        source: str | None,
        from_dt: datetime | None,
        to_dt: datetime | None,
        cursor: int | None,
    ) -> tuple[list, bool]:
        rows, has_more = await self.repository.list_paginated(
            self.tenant_id,
            agent_id=agent_id,
            rating=rating,
            source=source,
            from_dt=from_dt,
            to_dt=to_dt,
            cursor=cursor,
            limit=200,
        )
        if not rows:
            return rows, False

        message_ids = [row.message_id for row, _ in rows]
        session_keys = [(row.thread_id, row.session_id) for row, _ in rows]
        ai_by_id = await self.repository.get_ai_messages_by_ids(self.tenant_id, message_ids)
        trigger_keys = [
            (ai.thread_id, ai.trigger_message_id)
            for ai in ai_by_id.values()
            if ai.trigger_message_id
        ]
        human_by_trigger = await self.repository.get_human_contents_by_triggers(
            self.tenant_id,
            trigger_keys,
            truncate=False,
        )
        human_by_session = await self.repository.get_human_previews_for_sessions(
            session_keys,
            truncate=False,
        )

        for row, username in rows:
            ai_message = ai_by_id.get(row.message_id)
            human_message = _resolve_human_message(
                thread_id=row.thread_id,
                session_id=row.session_id,
                ai_message=ai_message,
                human_by_trigger=human_by_trigger,
                human_by_session=human_by_session,
            )
            exporter.append_row(
                [
                    row.id,
                    row.thread_id,
                    row.session_id or "",
                    row.message_id,
                    row.agent_id,
                    row.user_id,
                    username or "",
                    row.rating,
                    row.comment or "",
                    row.source,
                    human_message or "",
                    normalize_message_content(ai_message.content if ai_message else None) or "",
                    row.created_at.isoformat(),
                ]
            )

        return rows, has_more

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


FEEDBACK_EXPORT_HEADERS: tuple[str, ...] = (
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
    "human_message",
    "ai_message",
    "created_at",
)


async def iter_feedback_export_csv(
    tenant_id: int,
    *,
    agent_id: int | None = None,
    rating: str | None = None,
    source: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> AsyncIterator[bytes]:
    """Stream feedback CSV; one short-lived DB session per page (not held across client I/O)."""
    exporter = CsvTableExporter()
    exporter.write_header(FEEDBACK_EXPORT_HEADERS)
    header_chunk = exporter.flush_chunk()
    if header_chunk:
        yield header_chunk

    cursor: int | None = None
    while True:
        rows: list = []
        has_more = False
        async with app_db_session() as db:
            service = MessageFeedbackService(tenant_id, db)
            rows, has_more = await service._append_feedback_export_page(
                exporter,
                agent_id=agent_id,
                rating=rating,
                source=source,
                from_dt=from_dt,
                to_dt=to_dt,
                cursor=cursor,
            )

        if not rows:
            break

        page_chunk = exporter.flush_chunk()
        if page_chunk:
            yield page_chunk

        if not has_more:
            break
        cursor = rows[-1][0].id
