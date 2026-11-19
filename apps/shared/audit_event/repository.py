"""Repository utilities for audit events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AuditEvent, User, User

DEFAULT_PAGE_SIZE = 20
EXPORT_MAX_ROWS = 1000


class AuditEventRepository:
    """Data access layer for audit event writes and queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_event(
        self,
        *,
        tenant_id: int,
        actor_user_id: int | None,
        actor_type: str | None = None,
        event_type: str,
        outcome: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict | None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            event_type=event_type,
            outcome=outcome,
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_events(
        self,
        *,
        tenant_id: int,
        event_type: str | None = None,
        limit: int = 20,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        stmt = stmt.order_by(desc(AuditEvent.created_at)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _filtered_stmt(
        self,
        *,
        tenant_id: int,
        actor_user_id: int | None = None,
        event_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ):
        stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        if actor_user_id is not None:
            stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        if from_dt is not None:
            stmt = stmt.where(AuditEvent.created_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(AuditEvent.created_at <= to_dt)
        return stmt

    async def count_filtered(
        self,
        *,
        tenant_id: int,
        actor_user_id: int | None = None,
        event_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> int:
        base = self._filtered_stmt(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        stmt = select(func.count()).select_from(base.subquery())
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_paginated(
        self,
        *,
        tenant_id: int,
        actor_user_id: int | None = None,
        event_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[tuple[AuditEvent, str | None]], int]:
        total = await self.count_filtered(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        if total == 0:
            return [], 0
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size
        stmt = (
            select(AuditEvent, User.username)
            .select_from(AuditEvent)
            .outerjoin(
                User,
                (AuditEvent.actor_user_id == User.id) & (User.tenant_id == AuditEvent.tenant_id),
            )
            .where(AuditEvent.tenant_id == tenant_id)
        )
        if actor_user_id is not None:
            stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        if from_dt is not None:
            stmt = stmt.where(AuditEvent.created_at >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(AuditEvent.created_at <= to_dt)
        stmt = stmt.order_by(desc(AuditEvent.created_at), desc(AuditEvent.id)).offset(offset).limit(page_size)
        result = await self.db.execute(stmt)
        return [(event, username) for event, username in result.all()], total

    async def list_for_export(
        self,
        *,
        tenant_id: int,
        actor_user_id: int | None = None,
        event_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        limit: int = EXPORT_MAX_ROWS,
    ) -> tuple[list[AuditEvent], int, bool]:
        total = await self.count_filtered(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        truncated = total > limit
        stmt = (
            self._filtered_stmt(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                from_dt=from_dt,
                to_dt=to_dt,
            )
            .order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total, truncated