"""Portal branding (header/login) for tenant app chrome."""

from __future__ import annotations

import mimetypes
from io import BytesIO
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_file_storage
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import Tenant
from apps.shared.infra.storage.base import FileStorage
from apps.shared.infra.storage.paths import normalize_storage_key, resolve_storage_ref
from apps.shared.schemas.tenant import (
    PORTAL_BRANDING_AUTHENTICATED_LOGO_PATH,
    PortalBrandingDTO,
    UpdatePortalBrandingRequest,
    public_portal_branding_logo_path,
)
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.tenant.adapters import db_tenant_to_domain
from apps.tenant_app_service.tenant.domain import PortalBranding, TenantConfig, TenantDomain
from apps.tenant_app_service.tenant.repository import TenantRepository


def portal_branding_from_tenant(tenant: Tenant | TenantDomain) -> PortalBranding:
    """Read portal branding from a tenant ORM row or domain model."""
    if isinstance(tenant, TenantDomain):
        return tenant.config.portal_branding
    return TenantConfig.from_dict(tenant.config).portal_branding

logger = get_logger(__name__)

MAX_LOGO_BYTES = 512 * 1024
ALLOWED_LOGO_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

AUTHENTICATED_LOGO_PATH = PORTAL_BRANDING_AUTHENTICATED_LOGO_PATH


def public_logo_path(slug: str) -> str:
    return public_portal_branding_logo_path(slug)


class PortalBrandingService:
    def __init__(self, db: AsyncSession, file_storage: FileStorage | None = None):
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.file_storage = file_storage or get_file_storage()

    def _to_dto(self, branding: PortalBranding, *, logo_url: str | None) -> PortalBrandingDTO:
        return PortalBrandingDTO(
            app_title=branding.app_title,
            app_subtitle=branding.app_subtitle,
            page_title=branding.page_title,
            logo_url=logo_url,
        )

    def _authenticated_dto(self, branding: PortalBranding) -> PortalBrandingDTO:
        logo_url = AUTHENTICATED_LOGO_PATH if branding.logo_path else None
        return self._to_dto(branding, logo_url=logo_url)

    def _public_dto(self, branding: PortalBranding, slug: str) -> PortalBrandingDTO:
        logo_url = public_logo_path(slug) if branding.logo_path else None
        return self._to_dto(branding, logo_url=logo_url)

    async def get_for_tenant(self, tenant_id: int) -> PortalBrandingDTO:
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found", {"tenant_id": tenant_id})
        domain = db_tenant_to_domain(tenant)
        return self._authenticated_dto(domain.config.portal_branding)

    async def get_public_by_slug(self, slug: str) -> PortalBrandingDTO:
        domain = await self.tenant_repo.get_by_slug(slug)
        if not domain or not domain.is_active():
            raise ResourceNotFoundError("Tenant not found", {"slug": slug})
        return self._public_dto(domain.config.portal_branding, slug)

    async def update_for_tenant(
        self, tenant_id: int, request: UpdatePortalBrandingRequest
    ) -> PortalBrandingDTO:
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found", {"tenant_id": tenant_id})

        domain = db_tenant_to_domain(tenant)
        branding = domain.config.portal_branding
        updates = request.model_dump(exclude_unset=True)

        for field, raw in updates.items():
            if field not in {"app_title", "app_subtitle", "page_title"}:
                continue
            value: str | None
            if raw is None:
                value = None
            elif isinstance(raw, str):
                value = raw.strip() or None
            else:
                value = None
            setattr(branding, field, value)

        domain.config.portal_branding = branding
        merged_config = domain.config.to_dict()
        if tenant.config and isinstance(tenant.config, dict):
            merged_config = {**tenant.config, **merged_config}
            if domain.config.llm_defaults is None and "llm_defaults" in tenant.config:
                merged_config["llm_defaults"] = tenant.config["llm_defaults"]

        await self.tenant_repo.update_tenant(tenant_id, config=merged_config)
        logger.info("Updated portal branding for tenant %s", tenant_id)
        return self._authenticated_dto(branding)

    async def upload_logo(self, tenant_id: int, file: UploadFile) -> PortalBrandingDTO:
        content_type = (file.content_type or "").split(";")[0].strip().lower()
        ext = ALLOWED_LOGO_CONTENT_TYPES.get(content_type)
        if not ext:
            raise ValidationError(
                "Logo must be PNG, JPEG, WebP, or SVG",
                {"code": "PORTAL_LOGO_TYPE_INVALID"},
            )

        raw = await file.read()
        if not raw:
            raise ValidationError("Logo file is empty", {"code": "PORTAL_LOGO_EMPTY"})
        if len(raw) > MAX_LOGO_BYTES:
            raise ValidationError(
                "Logo must be 512 KB or smaller",
                {"code": "PORTAL_LOGO_TOO_LARGE"},
            )

        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found", {"tenant_id": tenant_id})

        domain = db_tenant_to_domain(tenant)
        branding = domain.config.portal_branding
        await self._delete_logo_file(tenant_id, branding.logo_path)

        filename = f"portal-logo{ext}"
        saved_key = await self.file_storage.save(str(tenant_id), filename, BytesIO(raw))
        branding.logo_path = normalize_storage_key(tenant_id, saved_key)

        domain.config.portal_branding = branding
        merged_config = self._merge_config_dict(tenant.config, domain.config.to_dict())
        await self.tenant_repo.update_tenant(tenant_id, config=merged_config)
        return self._authenticated_dto(branding)

    async def delete_logo(self, tenant_id: int) -> PortalBrandingDTO:
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found", {"tenant_id": tenant_id})

        domain = db_tenant_to_domain(tenant)
        branding = domain.config.portal_branding
        await self._delete_logo_file(tenant_id, branding.logo_path)
        branding.logo_path = None

        domain.config.portal_branding = branding
        merged_config = self._merge_config_dict(tenant.config, domain.config.to_dict())
        await self.tenant_repo.update_tenant(tenant_id, config=merged_config)
        return self._authenticated_dto(branding)

    async def read_logo_bytes(self, tenant_id: int) -> tuple[bytes, str]:
        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise ResourceNotFoundError("Tenant not found", {"tenant_id": tenant_id})
        domain = db_tenant_to_domain(tenant)
        return await self._read_logo(tenant_id, domain.config.portal_branding)

    async def read_logo_bytes_by_slug(self, slug: str) -> tuple[bytes, str]:
        domain = await self.tenant_repo.get_by_slug(slug)
        if not domain or not domain.is_active():
            raise ResourceNotFoundError("Tenant not found", {"slug": slug})
        return await self._read_logo(domain.id, domain.config.portal_branding)

    def branding_for_login_resolve(self, branding: PortalBranding, slug: str) -> PortalBrandingDTO:
        return self._public_dto(branding, slug)

    async def _read_logo(self, tenant_id: int, branding: PortalBranding) -> tuple[bytes, str]:
        if not branding.logo_path:
            raise ResourceNotFoundError("Logo not configured", {"code": "PORTAL_LOGO_NOT_FOUND"})
        resolved = resolve_storage_ref(tenant_id, branding.logo_path)
        try:
            content = await self.file_storage.read(resolved)
        except FileNotFoundError as e:
            raise ResourceNotFoundError("Logo file not found", {"code": "PORTAL_LOGO_NOT_FOUND"}) from e
        media_type = mimetypes.guess_type(branding.logo_path)[0] or "application/octet-stream"
        return content, media_type

    async def _delete_logo_file(self, tenant_id: int, logo_path: str | None) -> None:
        if not logo_path:
            return
        resolved = resolve_storage_ref(tenant_id, logo_path)
        try:
            await self.file_storage.delete(resolved)
        except Exception:
            logger.warning("Failed to delete previous portal logo at %s", resolved, exc_info=True)

    @staticmethod
    def _merge_config_dict(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
        if not existing:
            return patch
        merged = {**existing, **patch}
        if "llm_defaults" not in patch and "llm_defaults" in existing:
            merged["llm_defaults"] = existing["llm_defaults"]
        return merged
