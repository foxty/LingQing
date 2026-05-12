"""Repository for tenant manager P0 entities."""

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_manager_service.db.models import (
    TenantLifecycleEvent,
    TenantManagerAuditLog,
    TenantManagerTenant,
)


class TenantManagerRepository:
    """Repository for tenant and lifecycle persistence."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(self, tenant_uid: str, tenant_code: str, display_name: str) -> TenantManagerTenant:
        tenant = TenantManagerTenant(
            tenant_uid=tenant_uid,
            tenant_code=tenant_code,
            display_name=display_name,
            status="provisioning",
        )
        self.db.add(tenant)
        await self.db.flush()
        return tenant

    async def get_tenant_by_uid(self, tenant_uid: str) -> TenantManagerTenant | None:
        result = await self.db.execute(select(TenantManagerTenant).where(TenantManagerTenant.tenant_uid == tenant_uid))
        return result.scalar_one_or_none()

    async def get_tenant_by_code(self, tenant_code: str) -> TenantManagerTenant | None:
        result = await self.db.execute(
            select(TenantManagerTenant).where(TenantManagerTenant.tenant_code == tenant_code)
        )
        return result.scalar_one_or_none()

    async def list_tenants(self) -> list[TenantManagerTenant]:
        result = await self.db.execute(select(TenantManagerTenant).order_by(desc(TenantManagerTenant.updated_at)))
        return list(result.scalars().all())

    async def update_tenant_status(self, tenant: TenantManagerTenant, new_status: str) -> TenantManagerTenant:
        tenant.status = new_status
        tenant.updated_at = datetime.now(UTC)
        await self.db.flush()
        return tenant

    async def add_lifecycle_event(
        self,
        tenant_uid: str,
        event_type: str,
        from_status: str | None,
        to_status: str,
        operator_id: str | None,
        reason_code: str | None,
        event_metadata: dict | None = None,
    ) -> TenantLifecycleEvent:
        event = TenantLifecycleEvent(
            tenant_uid=tenant_uid,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            operator_id=operator_id,
            reason_code=reason_code,
            event_metadata=event_metadata,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_lifecycle_events(self, tenant_uid: str) -> list[TenantLifecycleEvent]:
        result = await self.db.execute(
            select(TenantLifecycleEvent)
            .where(TenantLifecycleEvent.tenant_uid == tenant_uid)
            .order_by(desc(TenantLifecycleEvent.created_at), desc(TenantLifecycleEvent.id))
        )
        return list(result.scalars().all())

    async def add_audit_log(
        self,
        tenant_uid: str | None,
        actor_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
        request_id: str | None,
        ip: str | None,
        before_snapshot: dict | None,
        after_snapshot: dict | None,
        details: str | None = None,
    ) -> TenantManagerAuditLog:
        audit_log = TenantManagerAuditLog(
            tenant_uid=tenant_uid,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            ip=ip,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            details=details,
        )
        self.db.add(audit_log)
        await self.db.flush()
        return audit_log
