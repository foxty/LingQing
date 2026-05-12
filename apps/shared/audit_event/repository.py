"""Repository utilities for audit events."""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AuditEvent


class AuditEventRepository:
    """Data access layer for audit event writes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_event(
        self,
        *,
        tenant_id: int,
        actor_user_id: int | None,
        event_type: str,
        payload: dict | None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
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
