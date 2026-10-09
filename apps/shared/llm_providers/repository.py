"""Repository adapters for tenant LLM providers and model profiles."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import LLMModelProfile, LLMProvider
from apps.shared.llm_providers.domain import (
    LLMModelProfileDomain,
    LLMProviderDomain,
    ModelProfileCategory,
    ModelProfileSource,
)

_UNSET: object = object()


def to_provider_domain(row: LLMProvider) -> LLMProviderDomain:
    return LLMProviderDomain(
        id=row.id,
        tenant_id=row.tenant_id,
        display_name=row.display_name,
        preset_key=row.preset_key,
        type=row.type,
        api_base=row.api_base,
        embedding_api_base=row.embedding_api_base,
        api_key_encrypted=row.api_key_encrypted,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_profile_domain(row: LLMModelProfile) -> LLMModelProfileDomain:
    return LLMModelProfileDomain(
        id=row.id,
        tenant_id=row.tenant_id,
        provider_id=row.provider_id,
        name=row.name,
        category=ModelProfileCategory(row.category),
        model_id=row.model_id,
        params=row.params,
        catalog_model_key=row.catalog_model_key,
        source=ModelProfileSource(row.source),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class LLMProviderRepository:
    """Tenant-scoped CRUD for llm_providers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_providers(self, tenant_id: int) -> list[LLMProviderDomain]:
        result = await self.db.execute(
            select(LLMProvider)
            .where(LLMProvider.tenant_id == tenant_id)
            .order_by(LLMProvider.display_name.asc())
        )
        return [to_provider_domain(row) for row in result.scalars().all()]

    async def get_provider(self, tenant_id: int, provider_id: int) -> LLMProviderDomain | None:
        result = await self.db.execute(
            select(LLMProvider).where(
                LLMProvider.tenant_id == tenant_id,
                LLMProvider.id == provider_id,
            )
        )
        row = result.scalar_one_or_none()
        return to_provider_domain(row) if row else None

    async def get_by_display_name(self, tenant_id: int, display_name: str) -> LLMProviderDomain | None:
        result = await self.db.execute(
            select(LLMProvider).where(
                LLMProvider.tenant_id == tenant_id,
                LLMProvider.display_name == display_name,
            )
        )
        row = result.scalar_one_or_none()
        return to_provider_domain(row) if row else None

    async def find_by_credentials(self, tenant_id: int, api_base: str, api_key_encrypted: str) -> LLMProviderDomain | None:
        result = await self.db.execute(
            select(LLMProvider).where(
                LLMProvider.tenant_id == tenant_id,
                LLMProvider.api_base == api_base,
                LLMProvider.api_key_encrypted == api_key_encrypted,
            )
        )
        row = result.scalar_one_or_none()
        return to_provider_domain(row) if row else None

    async def create_provider(
        self,
        *,
        tenant_id: int,
        display_name: str,
        preset_key: str | None,
        type: str,
        api_base: str,
        embedding_api_base: str | None,
        api_key_encrypted: str,
        status: str = "active",
    ) -> LLMProviderDomain:
        row = LLMProvider(
            tenant_id=tenant_id,
            display_name=display_name,
            preset_key=preset_key,
            type=type,
            api_base=api_base,
            embedding_api_base=embedding_api_base,
            api_key_encrypted=api_key_encrypted,
            status=status,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return to_provider_domain(row)

    async def update_provider(
        self,
        provider: LLMProviderDomain,
        *,
        display_name: str | None = None,
        preset_key: str | None = None,
        type: str | None = None,
        api_base: str | None = None,
        embedding_api_base: str | None | object = _UNSET,
        api_key_encrypted: str | None = None,
        status: str | None = None,
    ) -> LLMProviderDomain:
        result = await self.db.execute(
            select(LLMProvider).where(
                LLMProvider.tenant_id == provider.tenant_id,
                LLMProvider.id == provider.id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"LLM provider {provider.id} not found for tenant {provider.tenant_id}")

        if display_name is not None:
            row.display_name = display_name
        if preset_key is not None:
            row.preset_key = preset_key
        if type is not None:
            row.type = type
        if api_base is not None:
            row.api_base = api_base
        if embedding_api_base is not _UNSET:
            row.embedding_api_base = embedding_api_base  # type: ignore[assignment]
        if api_key_encrypted is not None:
            row.api_key_encrypted = api_key_encrypted
        if status is not None:
            row.status = status
        row.updated_at = datetime.now(UTC)

        await self.db.flush()
        await self.db.refresh(row)
        return to_provider_domain(row)

    async def delete_provider(self, tenant_id: int, provider_id: int) -> None:
        result = await self.db.execute(
            select(LLMProvider).where(
                LLMProvider.tenant_id == tenant_id,
                LLMProvider.id == provider_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        await self.db.delete(row)


class LLMModelProfileRepository:
    """Tenant-scoped CRUD for llm_model_profiles."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_profiles(
        self,
        tenant_id: int,
        *,
        category: ModelProfileCategory | None = None,
    ) -> list[LLMModelProfileDomain]:
        stmt = select(LLMModelProfile).where(LLMModelProfile.tenant_id == tenant_id)
        if category is not None:
            stmt = stmt.where(LLMModelProfile.category == category.value)
        stmt = stmt.order_by(LLMModelProfile.name.asc())
        result = await self.db.execute(stmt)
        return [to_profile_domain(row) for row in result.scalars().all()]

    async def get_profile(self, tenant_id: int, profile_id: int) -> LLMModelProfileDomain | None:
        result = await self.db.execute(
            select(LLMModelProfile).where(
                LLMModelProfile.tenant_id == tenant_id,
                LLMModelProfile.id == profile_id,
            )
        )
        row = result.scalar_one_or_none()
        return to_profile_domain(row) if row else None

    async def get_by_name(self, tenant_id: int, name: str) -> LLMModelProfileDomain | None:
        result = await self.db.execute(
            select(LLMModelProfile).where(
                LLMModelProfile.tenant_id == tenant_id,
                LLMModelProfile.name == name,
            )
        )
        row = result.scalar_one_or_none()
        return to_profile_domain(row) if row else None

    async def create_profile(
        self,
        *,
        tenant_id: int,
        provider_id: int,
        name: str,
        category: ModelProfileCategory,
        model_id: str,
        params: dict | None,
        catalog_model_key: str | None,
        source: ModelProfileSource,
    ) -> LLMModelProfileDomain:
        row = LLMModelProfile(
            tenant_id=tenant_id,
            provider_id=provider_id,
            name=name,
            category=category.value,
            model_id=model_id,
            params=params,
            catalog_model_key=catalog_model_key,
            source=source.value,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return to_profile_domain(row)

    async def update_profile(
        self,
        profile: LLMModelProfileDomain,
        *,
        name: str | None = None,
        model_id: str | None = None,
        params: dict | None = None,
        catalog_model_key: str | None = None,
        source: ModelProfileSource | None = None,
    ) -> LLMModelProfileDomain:
        result = await self.db.execute(
            select(LLMModelProfile).where(
                LLMModelProfile.tenant_id == profile.tenant_id,
                LLMModelProfile.id == profile.id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"LLM model profile {profile.id} not found for tenant {profile.tenant_id}")

        if name is not None:
            row.name = name
        if model_id is not None:
            row.model_id = model_id
        if params is not None:
            row.params = params
        if catalog_model_key is not None:
            row.catalog_model_key = catalog_model_key
        if source is not None:
            row.source = source.value
        row.updated_at = datetime.now(UTC)

        await self.db.flush()
        await self.db.refresh(row)
        return to_profile_domain(row)

    async def delete_profile(self, tenant_id: int, profile_id: int) -> None:
        result = await self.db.execute(
            select(LLMModelProfile).where(
                LLMModelProfile.tenant_id == tenant_id,
                LLMModelProfile.id == profile_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        await self.db.delete(row)

    async def count_profiles_for_provider(self, tenant_id: int, provider_id: int) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(LLMModelProfile)
            .where(
                LLMModelProfile.tenant_id == tenant_id,
                LLMModelProfile.provider_id == provider_id,
            )
        )
        return int(result.scalar_one() or 0)
