"""Tenant repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import Tenant
from apps.tenant_app_service.tenant.adapters import db_tenant_to_domain
from apps.tenant_app_service.tenant.domain import TenantConfig, TenantDomain


class TenantRepository(BaseRepository[Tenant]):
    """Repository for Tenant operations.

    Returns Domain models (TenantDomain) instead of DB models (Tenant).
    """

    def __init__(self, db: AsyncSession):
        """Initialize tenant repository.

        Args:
            db: Database session
        """
        super().__init__(Tenant, db)

    async def get_by_name(self, name: str) -> TenantDomain | None:
        """Get tenant by name.

        Args:
            name: Tenant name

        Returns:
            TenantDomain or None if not found
        """
        result = await self.db.execute(select(Tenant).where(Tenant.name == name))
        db_tenant = result.scalar_one_or_none()
        return db_tenant_to_domain(db_tenant) if db_tenant else None

    async def get_by_slug(self, slug: str) -> TenantDomain | None:
        """Get tenant by slug.

        Args:
            slug: Tenant slug

        Returns:
            TenantDomain or None if not found
        """
        result = await self.db.execute(select(Tenant).where(Tenant.slug == slug))
        db_tenant = result.scalar_one_or_none()
        return db_tenant_to_domain(db_tenant) if db_tenant else None

    async def get_active_tenants(self) -> list[TenantDomain]:
        """Get all active tenants.

        Returns:
            List of active TenantDomain
        """
        result = await self.db.execute(select(Tenant).where(Tenant.status == "active"))
        return [db_tenant_to_domain(t) for t in result.scalars().all()]

    async def create_tenant(
        self,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        config: dict | None = None,
    ) -> TenantDomain:
        """Create a new tenant.

        Args:
            name: Tenant display name (can be Chinese)
            slug: Tenant URL identifier (English, lowercase)
            description: Tenant description
            config: Tenant configuration (if None, initialize with default settings)

        Returns:
            Created TenantDomain
        """
        # Initialize with default config if not provided
        if config is None:
            default_config = TenantConfig()
            config = default_config.to_dict()

        tenant = Tenant(name=name, slug=slug, description=description, config=config, status="active")
        db_tenant = await self.create(tenant)
        return db_tenant_to_domain(db_tenant)

    async def update_tenant(
        self,
        tenant_id: int,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        config: dict | None = None,
        status: str | None = None,
    ) -> Tenant | None:
        """Update tenant.

        Args:
            tenant_id: Tenant ID
            name: New name
            slug: New slug (cannot be changed if already set)
            description: New description
            config: New config
            status: New status

        Returns:
            Updated tenant or None if not found
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return None

        if name is not None:
            tenant.name = name
        if slug is not None:
            tenant.slug = slug
        if description is not None:
            tenant.description = description
        if config is not None:
            tenant.config = config
        if status is not None:
            tenant.status = status

        return await self.update(tenant)
