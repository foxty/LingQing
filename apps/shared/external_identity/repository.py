"""Repository for external identities.

Tenant-scoped CRUD over the `external_identities` table. Implements the
persistence side of the identity binding port. No business logic.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ExternalIdentity, TenantMembership, User
from apps.tenant_app_service.auth.domain import MembershipStatus


class ExternalIdentityRepository:
    """Tenant-scoped data access for external_identities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_identity_by_subject(
        self, tenant_id: int, identity_source_id: int, external_subject: str
    ) -> ExternalIdentity | None:
        result = await self.db.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.tenant_id == tenant_id,
                ExternalIdentity.identity_source_id == identity_source_id,
                ExternalIdentity.external_subject == external_subject,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_identities(self, tenant_id: int) -> list[ExternalIdentity]:
        result = await self.db.execute(
            select(ExternalIdentity)
            .where(
                ExternalIdentity.tenant_id == tenant_id,
                ExternalIdentity.status == "pending",
            )
            .order_by(ExternalIdentity.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_identity(self, tenant_id: int, identity_id: int) -> ExternalIdentity | None:
        result = await self.db.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.tenant_id == tenant_id,
                ExternalIdentity.id == identity_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_identity(
        self,
        *,
        tenant_id: int,
        identity_source_id: int,
        external_subject: str,
        user_id: int | None,
        email: str | None,
        display_name: str | None,
        status: str,
    ) -> ExternalIdentity:
        row = ExternalIdentity(
            tenant_id=tenant_id,
            identity_source_id=identity_source_id,
            external_subject=external_subject,
            user_id=user_id,
            email=email,
            display_name=display_name,
            status=status,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_identity_status(
        self, tenant_id: int, identity_id: int, status: str, user_id: int | None = None
    ) -> ExternalIdentity | None:
        result = await self.db.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.tenant_id == tenant_id,
                ExternalIdentity.id == identity_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        row.status = status
        if user_id is not None:
            row.user_id = user_id
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def count_members_by_email(self, tenant_id: int, email: str) -> list[User]:
        """Return tenant members whose email matches (case-insensitive)."""
        normalized = email.lower()
        result = await self.db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == MembershipStatus.ACTIVE,
                User.email.is_not(None),
                func.lower(User.email) == normalized,
            )
        )
        return list(result.scalars().all())
