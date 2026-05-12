"""Skills management router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.skills.domain import SkillType
from apps.tenant_app_service.skills.dtos import (
    EnvVarListResponse,
    EnvVarUpdateRequest,
    SkillCreateResponse,
    SkillImportRequest,
    SkillInfo,
    SkillListResponse,
    SkillToggleRequest,
)
from apps.tenant_app_service.skills.service import SkillService

logger = get_logger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])


def _get_skill_service() -> SkillService:
    return SkillService()


@router.get("", response_model=SkillListResponse)
async def list_skills(
    type: str | None = Query(None, description="Filter by type: builtin/tenant/personal"),
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    type_filter = SkillType(type) if type else None
    skills = service.list_skills(current_user.tenant_id, current_user.id, type_filter=type_filter)
    return SkillListResponse(items=skills, total=len(skills))


@router.post("/import", response_model=SkillCreateResponse, status_code=201)
async def import_skill(
    payload: SkillImportRequest,
    type: str = Query(..., description="Skill type: tenant or personal"),
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    skill_type = SkillType(type)
    skill_info = service.import_skill_from_url(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        skill_type=skill_type,
        url=payload.url,
        created_by=str(current_user.id),
    )
    return SkillCreateResponse(name=skill_info.name, type=skill_type.value)


@router.get("/{name}", response_model=SkillInfo)
async def get_skill(
    name: str,
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    skill = service.get_skill(current_user.tenant_id, current_user.id, name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return skill


@router.post("", response_model=SkillCreateResponse, status_code=201)
async def create_skill(
    type: str = Query(..., description="Skill type: tenant or personal"),
    file: UploadFile = File(..., description="ZIP file containing SKILL.md and scripts"),
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are supported")

    skill_type = SkillType(type)
    skill_info = service.create_skill(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        skill_type=skill_type,
        zip_file=file.file,
        created_by=str(current_user.id),
    )

    return SkillCreateResponse(name=skill_info.name, type=skill_type.value)


@router.delete("/{name}", status_code=204)
async def delete_skill(
    name: str,
    type: str = Query(..., description="Skill type: tenant or personal"),
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    skill_type = SkillType(type)
    service.delete_skill(current_user.tenant_id, current_user.id, skill_type, name)


@router.get("/{scope}/{name}/env-vars", response_model=EnvVarListResponse)
async def list_env_vars(
    scope: str,
    name: str,
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    scope_type = SkillType(scope)
    env_vars = service.get_env_vars(current_user.tenant_id, current_user.id, scope_type, name)
    return EnvVarListResponse(env_vars=env_vars)


@router.patch("/{scope}/{name}/enabled", response_model=SkillInfo)
async def toggle_skill_enabled(
    scope: str,
    name: str,
    payload: SkillToggleRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    scope_type = SkillType(scope)
    skill = service.toggle_enabled(current_user.tenant_id, current_user.id, scope_type, name, payload.enabled)
    return skill


@router.put("/{scope}/{name}/env-vars", response_model=EnvVarListResponse)
async def update_env_vars(
    scope: str,
    name: str,
    payload: EnvVarUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.SKILLS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    service: SkillService = Depends(_get_skill_service),
):
    scope_type = SkillType(scope)
    masked = service.update_env_vars(current_user.tenant_id, current_user.id, scope_type, name, payload.env_vars)
    return EnvVarListResponse(env_vars=masked)
