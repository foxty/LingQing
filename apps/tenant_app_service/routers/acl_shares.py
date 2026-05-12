"""Shared ACL share management routes for non-artifact resources."""

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.auth import get_current_user
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.db.models import (
    AclGrant,
    Agent,
    ApiConnector,
    Dashboard,
    DataSource,
    DocumentCollection,
    LiveApp,
    Report,
    ResourceAcl,
    ScheduledTask,
    User,
)
from apps.shared.db.session import get_db
from apps.shared.domain.types import (
    ACL_PERMISSION_MANAGE,
    ACL_PERMISSION_READ,
    ACL_PERMISSION_WRITE,
    RESOURCE_TYPE_AGENT,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_APP,
    RESOURCE_TYPE_DASHBOARD,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
    RESOURCE_TYPE_REPORT,
    RESOURCE_TYPE_SCHEDULED_TASK,
    AclShareResourceType,
)
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/acl-shares", tags=["acl-shares"])


class AclShareRequest(BaseModel):
    """Request payload for creating/updating one user share grant."""

    user_id: int = Field(..., description="User ID to share with")
    permission: str = Field(default="read", description="Permission level: read or write")


class AclShareResponse(BaseModel):
    """ACL share row serialized for UI consumption."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_type: AclShareResourceType
    resource_id: int
    shared_with_user_id: int
    shared_with_username: str | None = None
    permission: str
    shared_by: int | None = None
    created_at: str


class AclShareListResponse(BaseModel):
    """GET /shares response: share rows plus caller's manage capability flag."""

    shares: list[AclShareResponse]
    can_manage: bool


class AclShareCandidateResponse(BaseModel):
    """Candidate user item for ACL share autocomplete."""

    id: int
    username: str


@dataclass(frozen=True)
class _ResourceShareConfig:
    model: Any
    manage_permission: str


_RESOURCE_SHARE_CONFIG: dict[AclShareResourceType, _ResourceShareConfig] = {
    RESOURCE_TYPE_DOCUMENT_COLLECTION: _ResourceShareConfig(
        model=DocumentCollection,
        manage_permission=Permissions.DOCUMENTS_MANAGE,
    ),
    RESOURCE_TYPE_API_CONNECTOR: _ResourceShareConfig(
        model=ApiConnector,
        manage_permission=Permissions.API_CONNECTORS_MANAGE,
    ),
    RESOURCE_TYPE_DATA_SOURCE: _ResourceShareConfig(
        model=DataSource,
        manage_permission=Permissions.DATA_SOURCES_MANAGE,
    ),
    RESOURCE_TYPE_DASHBOARD: _ResourceShareConfig(
        model=Dashboard,
        manage_permission=Permissions.DASHBOARDS_MANAGE,
    ),
    RESOURCE_TYPE_REPORT: _ResourceShareConfig(
        model=Report,
        manage_permission=Permissions.REPORTS_MANAGE,
    ),
    RESOURCE_TYPE_SCHEDULED_TASK: _ResourceShareConfig(
        model=ScheduledTask,
        manage_permission=Permissions.SCHEDULED_TASKS_MANAGE,
    ),
    RESOURCE_TYPE_APP: _ResourceShareConfig(
        model=LiveApp,
        manage_permission=Permissions.APPS_MANAGE,
    ),
    RESOURCE_TYPE_AGENT: _ResourceShareConfig(
        model=Agent,
        manage_permission=Permissions.AGENTS_MANAGE,
    ),
}

_PERMISSION_PRIORITY: dict[str, int] = {
    ACL_PERMISSION_READ: 1,
    ACL_PERMISSION_WRITE: 2,
    ACL_PERMISSION_MANAGE: 3,
}


def _normalize_display_permission(permission: str) -> str:
    return ACL_PERMISSION_WRITE if permission == ACL_PERMISSION_MANAGE else permission


def _validate_resource_type(resource_type: AclShareResourceType) -> _ResourceShareConfig:
    config = _RESOURCE_SHARE_CONFIG.get(resource_type)
    if not config:
        allowed = ", ".join(sorted(_RESOURCE_SHARE_CONFIG.keys()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported resource_type: {resource_type}. Allowed: {allowed}",
        )
    return config


async def _load_resource_and_owner(
    *,
    db: AsyncSession,
    tenant_id: int,
    resource_type: AclShareResourceType,
    resource_id: int,
) -> tuple[Any, int | None, _ResourceShareConfig]:
    config = _validate_resource_type(resource_type)
    model = config.model

    stmt = select(model).where(model.tenant_id == tenant_id, model.id == resource_id)

    resource = (await db.execute(stmt)).scalar_one_or_none()
    if resource is None:
        raise ResourceNotFoundError(f"{resource_type} {resource_id} not found")

    owner_id = getattr(resource, "owner_id", None)
    return resource, owner_id, config


async def _require_owner_or_manage(
    *,
    db: AsyncSession,
    current_user: UserDTO,
    resource_type: AclShareResourceType,
    resource_id: int,
) -> tuple[Any, int | None]:
    resource, owner_id, config = await _load_resource_and_owner(
        db=db,
        tenant_id=current_user.tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    if owner_id == current_user.id:
        return resource, owner_id

    has_manage = await role_has_permission(
        db=db,
        tenant_id=current_user.tenant_id,
        role_key=current_user.role,
        permission=config.manage_permission,
    )
    if has_manage:
        return resource, owner_id

    raise AuthorizationError("Only the owner or manager can manage shares")


async def _check_read_or_manage(
    *,
    db: AsyncSession,
    current_user: UserDTO,
    resource_type: AclShareResourceType,
    resource_id: int,
) -> bool:
    """Check whether the caller may view shares and whether they can manage them.

    Returns:
        True  — caller is owner or has resource manage permission (full CRUD).
        False — caller has an active ACL grant (read-only view of shares).

    Raises AuthorizationError if the caller has no access at all.
    """
    resource, owner_id, config = await _load_resource_and_owner(
        db=db,
        tenant_id=current_user.tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    if owner_id == current_user.id:
        return True

    has_manage = await role_has_permission(
        db=db,
        tenant_id=current_user.tenant_id,
        role_key=current_user.role,
        permission=config.manage_permission,
    )
    if has_manage:
        return True

    # Also allow any user who has an active ACL allow-grant on this resource (read-only).
    acl_stmt = select(ResourceAcl.id).where(
        ResourceAcl.tenant_id == current_user.tenant_id,
        ResourceAcl.resource_type == resource_type,
        ResourceAcl.resource_id == resource_id,
        ResourceAcl.status == "active",
    )
    resource_acl_id = (await db.execute(acl_stmt)).scalar_one_or_none()
    if resource_acl_id is not None:
        principal_filters = [and_(AclGrant.principal_type == "user", AclGrant.principal_id == str(current_user.id))]
        if current_user.role:
            principal_filters.append(
                and_(AclGrant.principal_type == "role", AclGrant.principal_id == current_user.role)
            )
        grant_stmt = select(AclGrant.id).where(
            AclGrant.tenant_id == current_user.tenant_id,
            AclGrant.resource_type == resource_type,
            AclGrant.resource_id == resource_id,
            AclGrant.effect == "allow",
            or_(*principal_filters),
        )
        grant_id = (await db.execute(grant_stmt)).scalar_one_or_none()
        if grant_id is not None:
            return False  # grantee: can view but not manage

    raise AuthorizationError("Only the owner or a user with access can view shares")


async def _ensure_resource_acl(
    *,
    db: AsyncSession,
    tenant_id: int,
    resource_type: AclShareResourceType,
    resource_id: int,
    owner_id: int | None,
) -> None:
    stmt = select(ResourceAcl).where(
        ResourceAcl.tenant_id == tenant_id,
        ResourceAcl.resource_type == resource_type,
        ResourceAcl.resource_id == resource_id,
    )
    resource_acl = (await db.execute(stmt)).scalar_one_or_none()

    if resource_acl is None:
        db.add(
            ResourceAcl(
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                owner_id=owner_id,
                status="active",
            )
        )
        await db.flush()
        return

    if resource_acl.owner_id is None and owner_id is not None:
        resource_acl.owner_id = owner_id
    if resource_acl.status != "active":
        resource_acl.status = "active"
    await db.flush()


async def _list_share_candidate_users(
    *,
    db: AsyncSession,
    tenant_id: int,
    resource_type: AclShareResourceType,
    resource_id: int,
    requester_user_id: int,
    query: str,
    limit: int,
) -> list[AclShareCandidateResponse]:
    shared_user_stmt = select(AclGrant.principal_id).where(
        AclGrant.tenant_id == tenant_id,
        AclGrant.resource_type == resource_type,
        AclGrant.resource_id == resource_id,
        AclGrant.principal_type == "user",
        AclGrant.effect == "allow",
    )
    shared_user_ids = {
        int(principal_id)
        for principal_id in (await db.execute(shared_user_stmt)).scalars().all()
        if str(principal_id).isdigit()
    }

    stmt = select(User.id, User.username).where(
        User.tenant_id == tenant_id,
        User.id != requester_user_id,
    )
    if shared_user_ids:
        stmt = stmt.where(User.id.not_in(shared_user_ids))

    normalized_query = query.strip().lower()
    if normalized_query:
        stmt = stmt.where(func.lower(User.username).like(f"%{normalized_query}%"))

    stmt = stmt.order_by(User.username.asc()).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [AclShareCandidateResponse(id=row.id, username=row.username) for row in rows]


@router.post(
    "/{resource_type}/{resource_id}/shares", response_model=AclShareResponse, status_code=status.HTTP_201_CREATED
)
async def share_resource(
    resource_type: AclShareResourceType,
    resource_id: int,
    request: AclShareRequest,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if request.permission not in {ACL_PERMISSION_READ, ACL_PERMISSION_WRITE}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission must be 'read' or 'write'")
    if request.user_id == current_user.id:
        raise AuthorizationError("Cannot share with yourself")

    _resource, owner_id = await _require_owner_or_manage(
        db=db,
        current_user=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    await _ensure_resource_acl(
        db=db,
        tenant_id=current_user.tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        owner_id=owner_id,
    )

    clear_stmt = delete(AclGrant).where(
        AclGrant.tenant_id == current_user.tenant_id,
        AclGrant.resource_type == resource_type,
        AclGrant.resource_id == resource_id,
        AclGrant.principal_type == "user",
        AclGrant.principal_id == str(request.user_id),
    )
    await db.execute(clear_stmt)

    grant = AclGrant(
        tenant_id=current_user.tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        principal_type="user",
        principal_id=str(request.user_id),
        permission=request.permission,
        effect="allow",
        created_by=current_user.id,
    )
    db.add(grant)
    await db.flush()
    await db.commit()

    user_stmt = select(User.username).where(User.id == request.user_id)
    shared_with_username = (await db.execute(user_stmt)).scalar_one_or_none()

    return AclShareResponse(
        id=grant.id,
        resource_type=resource_type,
        resource_id=resource_id,
        shared_with_user_id=request.user_id,
        shared_with_username=shared_with_username,
        permission=request.permission,
        shared_by=grant.created_by,
        created_at=grant.created_at.isoformat(),
    )


@router.get("/{resource_type}/{resource_id}/shares", response_model=AclShareListResponse)
async def list_resource_shares(
    resource_type: AclShareResourceType,
    resource_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    can_manage = await _check_read_or_manage(
        db=db,
        current_user=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    stmt = select(AclGrant).where(
        AclGrant.tenant_id == current_user.tenant_id,
        AclGrant.resource_type == resource_type,
        AclGrant.resource_id == resource_id,
        AclGrant.principal_type == "user",
        AclGrant.effect == "allow",
        AclGrant.permission.in_((ACL_PERMISSION_READ, ACL_PERMISSION_WRITE, ACL_PERMISSION_MANAGE)),
    )
    grant_rows = (await db.execute(stmt)).scalars().all()

    if not grant_rows:
        return AclShareListResponse(shares=[], can_manage=can_manage)

    best_grant_by_user: dict[int, AclGrant] = {}
    for grant in grant_rows:
        if not str(grant.principal_id).isdigit():
            continue
        user_id = int(grant.principal_id)
        existing = best_grant_by_user.get(user_id)
        if existing is None or _PERMISSION_PRIORITY.get(grant.permission, 0) > _PERMISSION_PRIORITY.get(
            existing.permission, 0
        ):
            best_grant_by_user[user_id] = grant

    user_ids = list(best_grant_by_user.keys())
    username_map: dict[int, str | None] = {}
    if user_ids:
        users_stmt = select(User.id, User.username).where(User.id.in_(user_ids))
        user_rows = (await db.execute(users_stmt)).all()
        username_map = {row.id: row.username for row in user_rows}

    ordered_grants = sorted(best_grant_by_user.values(), key=lambda row: row.created_at)
    shares = [
        AclShareResponse(
            id=grant.id,
            resource_type=resource_type,
            resource_id=resource_id,
            shared_with_user_id=int(grant.principal_id),
            shared_with_username=username_map.get(int(grant.principal_id)),
            permission=_normalize_display_permission(grant.permission),
            shared_by=grant.created_by,
            created_at=grant.created_at.isoformat(),
        )
        for grant in ordered_grants
    ]
    return AclShareListResponse(shares=shares, can_manage=can_manage)


@router.get("/{resource_type}/{resource_id}/candidates", response_model=list[AclShareCandidateResponse])
async def list_share_candidates(
    resource_type: AclShareResourceType,
    resource_id: int,
    q: str = Query(default="", description="Username keyword for autocomplete search"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum number of candidates to return"),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owner_or_manage(
        db=db,
        current_user=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return await _list_share_candidate_users(
        db=db,
        tenant_id=current_user.tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        requester_user_id=current_user.id,
        query=q,
        limit=limit,
    )


@router.delete("/{resource_type}/{resource_id}/shares/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_resource_share(
    resource_type: AclShareResourceType,
    resource_id: int,
    user_id: int = Path(..., description="User ID to revoke share from"),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_owner_or_manage(
        db=db,
        current_user=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    stmt = delete(AclGrant).where(
        AclGrant.tenant_id == current_user.tenant_id,
        AclGrant.resource_type == resource_type,
        AclGrant.resource_id == resource_id,
        AclGrant.principal_type == "user",
        AclGrant.principal_id == str(user_id),
    )
    result = await db.execute(stmt)
    if not result.rowcount:
        raise ResourceNotFoundError(f"Share not found for user {user_id}")

    await db.commit()
