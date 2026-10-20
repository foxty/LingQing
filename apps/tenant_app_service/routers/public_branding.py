"""Public tenant portal branding (login chrome)."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.session import get_db
from apps.shared.schemas.tenant import PortalBrandingDTO
from apps.tenant_app_service.tenant.portal_branding_service import PortalBrandingService

router = APIRouter(prefix="/public", tags=["public"], include_in_schema=False)


@router.get("/tenants/{slug}/portal-branding", response_model=PortalBrandingDTO)
async def get_public_portal_branding(slug: str, db: AsyncSession = Depends(get_db)):
    service = PortalBrandingService(db)
    return await service.get_public_by_slug(slug)


@router.get("/tenants/{slug}/portal-branding/logo")
async def get_public_portal_logo(slug: str, db: AsyncSession = Depends(get_db)):
    service = PortalBrandingService(db)
    content, media_type = await service.read_logo_bytes_by_slug(slug)
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "public, max-age=300"})
