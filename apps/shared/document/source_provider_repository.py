"""Tenant-scoped repository for document source provider config."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import DocumentSourceProvider
from apps.shared.document.sync_types import (
    DEFAULT_DOCUMENT_SOURCE_PROVIDER,
    SENSITIVE_PROVIDER_CONFIG_FIELDS,
)
from apps.shared.utils.field_cipher import FieldCipher


class DocumentSourceProviderRepository:
    """CRUD for tenant-level external document source OAuth config."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cipher = FieldCipher()

    async def get_provider(
        self,
        tenant_id: int,
        provider: str = DEFAULT_DOCUMENT_SOURCE_PROVIDER,
    ) -> DocumentSourceProvider | None:
        result = await self.db.execute(
            select(DocumentSourceProvider).where(
                DocumentSourceProvider.tenant_id == tenant_id,
                DocumentSourceProvider.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def get_provider_by_id(self, tenant_id: int, provider_id: int) -> DocumentSourceProvider | None:
        result = await self.db.execute(
            select(DocumentSourceProvider).where(
                DocumentSourceProvider.tenant_id == tenant_id,
                DocumentSourceProvider.id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_provider(
        self,
        *,
        tenant_id: int,
        provider: str,
        enabled: bool,
        config: dict,
    ) -> DocumentSourceProvider:
        row = await self.get_provider(tenant_id, provider)
        encrypted = self._cipher.encrypt_dict(config, sensitive_fields=SENSITIVE_PROVIDER_CONFIG_FIELDS)
        if row is None:
            row = DocumentSourceProvider(
                tenant_id=tenant_id,
                provider=provider,
                enabled=enabled,
                config_json=encrypted,
            )
            self.db.add(row)
        else:
            row.enabled = enabled
            row.config_json = encrypted
        await self.db.flush()
        await self.db.refresh(row)
        return row

    def decrypt_config(self, provider: DocumentSourceProvider) -> dict:
        return self._cipher.decrypt_dict(provider.config_json or {})

    def encrypt_config(self, config: dict) -> dict:
        return self._cipher.encrypt_dict(config, sensitive_fields=SENSITIVE_PROVIDER_CONFIG_FIELDS)

    def merge_config_update(self, existing: dict, update: dict) -> dict:
        merged = dict(existing)
        for key, value in update.items():
            if key == "client_secret" and not value:
                continue
            merged[key] = value
        return merged
