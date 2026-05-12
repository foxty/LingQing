"""Tenant-scoped repository for identity admin tables."""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import Tenant, TenantLoginDomain, TenantMembership
from apps.tenant_app_service.auth.domain import MembershipStatus


class IdentityRepository:
    """Login domains, force-SSO settings, and break-glass membership flags."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_domains(self, tenant_id: int) -> list[TenantLoginDomain]:
        result = await self.db.execute(
            select(TenantLoginDomain).where(TenantLoginDomain.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def get_domain(self, domain: str) -> TenantLoginDomain | None:
        result = await self.db.execute(
            select(TenantLoginDomain).where(TenantLoginDomain.domain == domain.lower())
        )
        return result.scalar_one_or_none()

    async def add_domain(self, tenant_id: int, domain: str) -> TenantLoginDomain:
        row = TenantLoginDomain(tenant_id=tenant_id, domain=domain.lower())
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def remove_domain(self, tenant_id: int, domain_id: int) -> bool:
        result = await self.db.execute(
            delete(TenantLoginDomain).where(
                TenantLoginDomain.tenant_id == tenant_id,
                TenantLoginDomain.id == domain_id,
            )
        )
        await self.db.flush()
        return result.rowcount > 0

    async def get_tenant(self, tenant_id: int) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def set_force_sso(self, tenant_id: int, force_sso: bool) -> None:
        await self.db.execute(update(Tenant).where(Tenant.id == tenant_id).values(force_sso=force_sso))
        await self.db.flush()

    async def count_break_glass_admins(self, tenant_id: int) -> int:
        result = await self.db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == MembershipStatus.ACTIVE,
                TenantMembership.is_break_glass.is_(True),
            )
        )
        return len(list(result.scalars().all()))

    async def set_membership_break_glass(
        self, tenant_id: int, user_id: int, is_break_glass: bool
    ) -> TenantMembership | None:
        result = await self.db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        row.is_break_glass = is_break_glass
        await self.db.flush()
        return row
