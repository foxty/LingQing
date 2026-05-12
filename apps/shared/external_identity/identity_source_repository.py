"""Repository for identity_sources — neutral anchor for external identity bindings."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import IdentitySource
from apps.shared.external_identity.domain import (
    POLICY_REJECT,
    SOURCE_KIND_LOGIN_PROVIDER,
    login_provider_source_key,
    validate_policy,
)


class IdentitySourceRepository:
    """Tenant-scoped CRUD for identity_sources."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, tenant_id: int, source_id: int) -> IdentitySource | None:
        result = await self.db.execute(
            select(IdentitySource).where(
                IdentitySource.tenant_id == tenant_id,
                IdentitySource.id == source_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: int) -> list[IdentitySource]:
        result = await self.db.execute(
            select(IdentitySource)
            .where(IdentitySource.tenant_id == tenant_id)
            .order_by(IdentitySource.source_kind.asc(), IdentitySource.display_name.asc())
        )
        return list(result.scalars().all())

    async def get_by_source_key(self, tenant_id: int, source_key: str) -> IdentitySource | None:
        result = await self.db.execute(
            select(IdentitySource).where(
                IdentitySource.tenant_id == tenant_id,
                IdentitySource.source_key == source_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_login_provider_source(
        self, tenant_id: int, auth_provider_id: int
    ) -> IdentitySource | None:
        return await self.get_by_source_key(tenant_id, login_provider_source_key(auth_provider_id))

    async def create_login_provider_source(
        self,
        *,
        tenant_id: int,
        display_name: str,
        bind_policy: str,
    ) -> IdentitySource:
        validate_policy(bind_policy)
        row = IdentitySource(
            tenant_id=tenant_id,
            source_kind=SOURCE_KIND_LOGIN_PROVIDER,
            source_key=f"oidc:pending:{uuid4().hex}",
            display_name=display_name,
            bind_policy=bind_policy,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def finalize_login_provider_source_key(
        self, source: IdentitySource, auth_provider_id: int
    ) -> IdentitySource:
        source.source_key = login_provider_source_key(auth_provider_id)
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def ensure_login_provider_source(
        self,
        *,
        tenant_id: int,
        auth_provider_id: int,
        display_name: str,
        bind_policy: str | None = None,
    ) -> IdentitySource:
        source_key = login_provider_source_key(auth_provider_id)
        existing = await self.get_by_source_key(tenant_id, source_key)
        if existing:
            if existing.display_name != display_name:
                existing.display_name = display_name
                await self.db.flush()
            return existing
        row = IdentitySource(
            tenant_id=tenant_id,
            source_kind=SOURCE_KIND_LOGIN_PROVIDER,
            source_key=source_key,
            display_name=display_name,
            bind_policy=bind_policy or POLICY_REJECT,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_bind_policy(
        self, tenant_id: int, source_id: int, bind_policy: str
    ) -> IdentitySource:
        validate_policy(bind_policy)
        source = await self.get_by_id(tenant_id, source_id)
        if not source:
            raise ValueError("Identity source not found")
        source.bind_policy = bind_policy
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def sync_display_name(self, source: IdentitySource, display_name: str) -> IdentitySource:
        if source.display_name != display_name:
            source.display_name = display_name
            await self.db.flush()
            await self.db.refresh(source)
        return source
