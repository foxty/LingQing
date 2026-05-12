"""Tenant lifecycle routes for tenant manager service."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.tm_permissions import TenantManagerPermissions as Permissions
from apps.tenant_manager_service.core.auth import require_tm_permission
from apps.tenant_manager_service.db.session import get_tenant_manager_db
from apps.tenant_manager_service.repositories.tenant_repository import TenantManagerRepository
from apps.tenant_manager_service.schemas import (
    TenantCreateRequest,
    TenantLifecycleEventResponse,
    TenantListResponse,
    TenantResponse,
    TenantStatusActionRequest,
    TMPrincipal,
)
from apps.tenant_manager_service.services.tenant_lifecycle_service import TenantLifecycleService

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _build_service(db: AsyncSession) -> TenantLifecycleService:
    repository = TenantManagerRepository(db)
    return TenantLifecycleService(repository)


@router.post("", response_model=TenantResponse)
async def create_tenant(
    payload: TenantCreateRequest,
    request: Request,
    current_user: TMPrincipal = Depends(require_tm_permission(Permissions.TENANTS_CREATE)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Create tenant in provisioning status."""
    service = _build_service(db)
    tenant = await service.create_tenant(
        tenant_code=payload.tenant_code,
        display_name=payload.display_name,
        actor_id=current_user.sub,
        request_id=request.headers.get("x-request-id"),
        ip=request.client.host if request.client else None,
    )
    return TenantResponse.model_validate(tenant)


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    _: TMPrincipal = Depends(require_tm_permission(Permissions.TENANTS_READ)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """List tenants."""
    service = _build_service(db)
    tenants = await service.list_tenants()
    return TenantListResponse(items=[TenantResponse.model_validate(item) for item in tenants])


@router.get("/{tenant_uid}", response_model=TenantResponse)
async def get_tenant(
    tenant_uid: str,
    _: TMPrincipal = Depends(require_tm_permission(Permissions.TENANTS_READ)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Get tenant by tenant_uid."""
    service = _build_service(db)
    tenant = await service.get_tenant(tenant_uid)
    return TenantResponse.model_validate(tenant)


@router.post("/{tenant_uid}/provision", response_model=TenantResponse)
async def provision_tenant(
    tenant_uid: str,
    payload: TenantStatusActionRequest,
    request: Request,
    current_user: TMPrincipal = Depends(require_tm_permission(Permissions.LIFECYCLE_PROVISION)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Transition tenant from provisioning to active."""
    service = _build_service(db)
    tenant = await service.provision_tenant(
        tenant_uid=tenant_uid,
        actor_id=current_user.sub,
        reason_code=payload.reason_code,
        request_id=request.headers.get("x-request-id"),
        ip=request.client.host if request.client else None,
    )
    return TenantResponse.model_validate(tenant)


@router.post("/{tenant_uid}/lock", response_model=TenantResponse)
async def lock_tenant(
    tenant_uid: str,
    payload: TenantStatusActionRequest,
    request: Request,
    current_user: TMPrincipal = Depends(require_tm_permission(Permissions.LIFECYCLE_LOCK)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Transition tenant from active to locked."""
    service = _build_service(db)
    tenant = await service.lock_tenant(
        tenant_uid=tenant_uid,
        actor_id=current_user.sub,
        reason_code=payload.reason_code,
        request_id=request.headers.get("x-request-id"),
        ip=request.client.host if request.client else None,
    )
    return TenantResponse.model_validate(tenant)


@router.post("/{tenant_uid}/unlock", response_model=TenantResponse)
async def unlock_tenant(
    tenant_uid: str,
    payload: TenantStatusActionRequest,
    request: Request,
    current_user: TMPrincipal = Depends(require_tm_permission(Permissions.LIFECYCLE_UNLOCK)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Transition tenant from locked to active."""
    service = _build_service(db)
    tenant = await service.unlock_tenant(
        tenant_uid=tenant_uid,
        actor_id=current_user.sub,
        reason_code=payload.reason_code,
        request_id=request.headers.get("x-request-id"),
        ip=request.client.host if request.client else None,
    )
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_uid}/lifecycle-events", response_model=list[TenantLifecycleEventResponse])
async def list_lifecycle_events(
    tenant_uid: str,
    _: TMPrincipal = Depends(require_tm_permission(Permissions.TENANTS_READ)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """List tenant lifecycle events."""
    service = _build_service(db)
    events = await service.list_lifecycle_events(tenant_uid)
    return [TenantLifecycleEventResponse.model_validate(item) for item in events]
