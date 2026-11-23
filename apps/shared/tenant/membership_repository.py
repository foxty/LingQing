"""Tenant membership reads (infrastructure)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import TenantMembership, User
from apps.shared.domain.membership import MembershipStatus, UserAccountStatus


class TenantMembershipRepository:
    """Tenant-scoped membership lookups."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_member_user(self, *, tenant_id: int, user_id: int) -> User | None:
        result = await self.db.execute(
            select(User, TenantMembership)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
                TenantMembership.status == MembershipStatus.ACTIVE,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        user, _membership = row
        if getattr(user, "status", UserAccountStatus.ACTIVE) != UserAccountStatus.ACTIVE:
            return None
        return user