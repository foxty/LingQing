"""User tag binding router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.domain.types import RESOURCE_TYPE_USER
from apps.shared.schemas.user import UserDTO
from apps.shared.tag.adapters import domain_tag_value_to_api
from apps.shared.tag.schemas import TagBindingCreateRequest, TagValueDTO
from apps.shared.tag.service import TagService
from apps.tenant_app_service.auth.repository import UserRepository

router = APIRouter(prefix="/users", tags=["users"], include_in_schema=False)


def _create_tag_service(db: AsyncSession, tenant_id: int) -> TagService:
    return TagService.create(tenant_id, db)


async def _get_user_or_404(db: AsyncSession, tenant_id: int, user_id: int):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id_and_tenant(user_id, tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}/tags", response_model=list[TagValueDTO])
async def list_user_tags(
    user_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_or_404(db, current_user.tenant_id, user_id)
    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_values = await tag_service.list_tags_for_resource(RESOURCE_TYPE_USER, user_id)
    return [domain_tag_value_to_api(tag_value) for tag_value in tag_values]


@router.post("/{user_id}/tags", response_model=TagValueDTO)
async def bind_user_tag(
    user_id: int,
    payload: TagBindingCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_or_404(db, current_user.tenant_id, user_id)
    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await tag_service.bind_tag_value(
        resource_type=RESOURCE_TYPE_USER,
        resource_id=user_id,
        tag_value_id=payload.tag_value_id,
        created_by=current_user.id,
    )
    return domain_tag_value_to_api(tag_value)


@router.delete("/{user_id}/tags/{tag_value_id}", status_code=204)
async def unbind_user_tag(
    user_id: int,
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_or_404(db, current_user.tenant_id, user_id)
    tag_service = _create_tag_service(db, current_user.tenant_id)
    await tag_service.unbind_tag_value(
        resource_type=RESOURCE_TYPE_USER,
        resource_id=user_id,
        tag_value_id=tag_value_id,
    )
