"""Tag system router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.domain.types import ResourceType
from apps.shared.schemas.user import UserDTO
from apps.shared.tag.adapters import (
    domain_resource_tag_config_to_api,
    domain_tag_key_to_api,
    domain_tag_value_to_api,
)
from apps.shared.tag.schemas import (
    ResourceTagConfigCreateRequest,
    ResourceTagConfigDTO,
    ResourceTagConfigUpdateRequest,
    TagKeyCreateRequest,
    TagKeyDTO,
    TagKeyUpdateRequest,
    TagValueCreateRequest,
    TagValueDTO,
    TagValueUpdateRequest,
)
from apps.shared.tag.service import TagService

router = APIRouter(tags=["tags"], include_in_schema=False)


def _create_tag_service(db: AsyncSession, tenant_id: int) -> TagService:
    return TagService.create(tenant_id, db)


@router.get("/tags/keys", response_model=list[TagKeyDTO])
async def list_tag_keys(
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_keys = await service.list_tag_keys()
    return [domain_tag_key_to_api(tag_key) for tag_key in tag_keys]


@router.post("/tags/keys", response_model=TagKeyDTO)
async def create_tag_key(
    payload: TagKeyCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_key = await service.create_tag_key(
        name=payload.name,
        description=payload.description,
        color=payload.color,
        created_by=current_user.id,
    )
    return domain_tag_key_to_api(tag_key)


@router.get("/tags/keys/{tag_key_id}", response_model=TagKeyDTO)
async def get_tag_key(
    tag_key_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_key = await service.get_tag_key(tag_key_id)
    if not tag_key:
        raise HTTPException(status_code=404, detail="TagKey not found")
    return domain_tag_key_to_api(tag_key)


@router.patch("/tags/keys/{tag_key_id}", response_model=TagKeyDTO)
async def update_tag_key(
    tag_key_id: int,
    payload: TagKeyUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_key = await service.update_tag_key(
        tag_key_id=tag_key_id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        updated_by=current_user.id,
    )
    return domain_tag_key_to_api(tag_key)


@router.patch("/tags/keys/{tag_key_id}/disable", response_model=TagKeyDTO)
async def disable_tag_key(
    tag_key_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_key = await service.disable_tag_key(tag_key_id, updated_by=current_user.id)
    return domain_tag_key_to_api(tag_key)


@router.patch("/tags/keys/{tag_key_id}/enable", response_model=TagKeyDTO)
async def enable_tag_key(
    tag_key_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_key = await service.enable_tag_key(tag_key_id, updated_by=current_user.id)
    return domain_tag_key_to_api(tag_key)


@router.delete("/tags/keys/{tag_key_id}", status_code=204)
async def delete_tag_key(
    tag_key_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    await service.delete_tag_key(tag_key_id)


@router.get("/tags/values", response_model=list[TagValueDTO])
async def list_tag_values(
    key_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_values = await service.list_tag_values(key_id=key_id)
    return [domain_tag_value_to_api(tag_value) for tag_value in tag_values]


@router.post("/tags/values", response_model=TagValueDTO)
async def create_tag_value(
    payload: TagValueCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await service.create_tag_value(
        key_id=payload.key_id,
        value=payload.value,
        rank=payload.rank,
        created_by=current_user.id,
    )
    return domain_tag_value_to_api(tag_value)


@router.get("/tags/values/{tag_value_id}", response_model=TagValueDTO)
async def get_tag_value(
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await service.get_tag_value(tag_value_id)
    if not tag_value:
        raise HTTPException(status_code=404, detail="TagValue not found")
    return domain_tag_value_to_api(tag_value)


@router.patch("/tags/values/{tag_value_id}", response_model=TagValueDTO)
async def update_tag_value(
    tag_value_id: int,
    payload: TagValueUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await service.update_tag_value(
        tag_value_id=tag_value_id,
        value=payload.value,
        rank=payload.rank,
        rank_provided="rank" in payload.model_fields_set,
        updated_by=current_user.id,
    )
    return domain_tag_value_to_api(tag_value)


@router.patch("/tags/values/{tag_value_id}/disable", response_model=TagValueDTO)
async def disable_tag_value(
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await service.disable_tag_value(tag_value_id, updated_by=current_user.id)
    return domain_tag_value_to_api(tag_value)


@router.patch("/tags/values/{tag_value_id}/enable", response_model=TagValueDTO)
async def enable_tag_value(
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await service.enable_tag_value(tag_value_id, updated_by=current_user.id)
    return domain_tag_value_to_api(tag_value)


@router.delete("/tags/values/{tag_value_id}", status_code=204)
async def delete_tag_value(
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    await service.delete_tag_value(tag_value_id)


@router.get("/resource-tag-configs", response_model=list[ResourceTagConfigDTO])
async def list_resource_tag_configs(
    resource_type: ResourceType | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    resource_tags = await service.list_resource_tag_configs(resource_type=resource_type)
    return [domain_resource_tag_config_to_api(resource_tag) for resource_tag in resource_tags]


@router.post("/resource-tag-configs", response_model=ResourceTagConfigDTO)
async def create_resource_tag_config(
    payload: ResourceTagConfigCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    resource_tag = await service.create_resource_tag_config(
        resource_type=payload.resource_type,
        tag_key_id=payload.tag_key_id,
        value_mode=payload.value_mode,
        created_by=current_user.id,
    )
    return domain_resource_tag_config_to_api(resource_tag)


@router.get("/resource-tag-configs/{config_id}", response_model=ResourceTagConfigDTO)
async def get_resource_tag_config(
    config_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    resource_tag = await service.get_resource_tag_config(config_id)
    if not resource_tag:
        raise HTTPException(status_code=404, detail="ResourceTagConfig not found")
    return domain_resource_tag_config_to_api(resource_tag)


@router.patch("/resource-tag-configs/{config_id}", response_model=ResourceTagConfigDTO)
async def update_resource_tag_config(
    config_id: int,
    payload: ResourceTagConfigUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    resource_tag = await service.update_resource_tag_config(
        config_id=config_id,
        value_mode=payload.value_mode,
    )
    return domain_resource_tag_config_to_api(resource_tag)


@router.delete("/resource-tag-configs/{config_id}", status_code=204)
async def delete_resource_tag_config(
    config_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_tag_service(db, current_user.tenant_id)
    await service.delete_resource_tag_config(config_id)
