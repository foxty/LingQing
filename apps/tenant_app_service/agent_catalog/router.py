"""HTTP routes for custom agent catalog."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.transaction import transaction
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills
from apps.tenant_app_service.agent_catalog.dtos import (
    AgentCreateRequest,
    AgentResponse,
    AgentSkillCatalogItem,
    AgentUpdateRequest,
)
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService

router = APIRouter(prefix="/agents", tags=["agents"])


def _actor(user: UserDTO) -> ActorContext:
    return ActorContext(tenant_id=user.tenant_id, user_id=user.id, user_role=user.role)


def _service(db: AsyncSession, tenant_id: int) -> AgentCatalogService:
    return AgentCatalogService(tenant_id=tenant_id, db_session=db)


def _assignable_skills(user: UserDTO):
    return resolve_assignable_skills(tenant_id=user.tenant_id, user_id=user.id)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db, current_user.tenant_id).list_agents_for_actor(
        actor=_actor(current_user),
        assignable_skills=_assignable_skills(current_user),
    )


@router.get("/catalog/skills", response_model=list[AgentSkillCatalogItem])
async def list_assignable_skills(
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return [
        AgentSkillCatalogItem(
            name=skill.name,
            description=skill.description,
            scope=skill.scope,
            tools=list(skill.tools),
        )
        for skill in _assignable_skills(current_user)
        if skill.is_shareable
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db, current_user.tenant_id).get_agent_for_actor(
        agent_id=agent_id,
        actor=_actor(current_user),
        assignable_skills=_assignable_skills(current_user),
    )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
@transaction
async def create_agent(
    payload: AgentCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db, current_user.tenant_id).create_agent(
        payload=payload,
        actor=_actor(current_user),
        assignable_skills=_assignable_skills(current_user),
    )


@router.put("/{agent_id}", response_model=AgentResponse)
@transaction
async def update_agent(
    agent_id: int,
    payload: AgentUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db, current_user.tenant_id).update_agent(
        agent_id=agent_id,
        payload=payload,
        actor=_actor(current_user),
        assignable_skills=_assignable_skills(current_user),
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
@transaction
async def delete_agent(
    agent_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    await _service(db, current_user.tenant_id).delete_agent(agent_id=agent_id, actor=_actor(current_user))
