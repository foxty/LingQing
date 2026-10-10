"""Shared tenant persistence adapter (ORM-level, cross-cutting reads)."""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import Tenant


class TenantRepository(BaseRepository[Tenant]):
    """CRUD adapter for ``Tenant`` rows usable from shared/core and services."""

    def __init__(self, db: AsyncSession):
        super().__init__(Tenant, db)
