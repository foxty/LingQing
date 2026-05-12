"""Helpers for loading tenant-scoped configuration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import Tenant


async def load_tenant_config(session: AsyncSession, tenant_id: int) -> dict | None:
    """Return tenant.config JSON for embedding and model settings."""
    result = await session.execute(select(Tenant.config).where(Tenant.id == tenant_id))
    config = result.scalar_one_or_none()
    return config if isinstance(config, dict) else None
