"""Tenant-scoped user search for collaboration pickers (not admin user management)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import TenantMembership, User
from apps.tenant_app_service.auth.domain import MEMBERSHIP_ACTIVE


async def search_tenant_users(
    db: AsyncSession,
    *,
    tenant_id: int,
    query: str = "",
    limit: int = 20,
    exclude_user_ids: set[int] | None = None,
) -> list[tuple[int, str]]:
    """Return (user_id, username) for active tenant members matching ``query``."""
    stmt = (
        select(User.id, User.username)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == MEMBERSHIP_ACTIVE,
        )
    )
    excluded = exclude_user_ids or set()
    if excluded:
        stmt = stmt.where(User.id.not_in(excluded))

    normalized = query.strip().lower()
    if normalized:
        stmt = stmt.where(func.lower(User.username).like(f"%{normalized}%"))

    stmt = stmt.order_by(User.username.asc()).limit(min(max(limit, 1), 50))
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def usernames_for_user_ids(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_ids: list[int],
) -> dict[int, str]:
    if not user_ids:
        return {}
    result = await db.execute(
        select(User.id, User.username)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            User.id.in_(user_ids),
        )
    )
    return {row[0]: row[1] for row in result.all()}
