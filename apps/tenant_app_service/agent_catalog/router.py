"""HTTP routes for custom agent catalog."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import ValidationError
from apps.shared.core.transaction import transaction
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.observability.dtos import TenantUsageStatsDTO
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills
from apps.tenant_app_service.agent_catalog.domain import sorted_platform_capabilities
from apps.tenant_app_service.agent_catalog.dtos import (
    AgentCreateRequest,
    AgentResponse,
    AgentSkillCatalogItem,
    AgentUpdateRequest,
)
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
from apps.tenant_app_service.tenant.schemas import TokenUsageDailyPoint, TokenUsageEventsResponse

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


@router.get("/catalog/platform-capabilities", response_model=list[str])
async def list_platform_capabilities(
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
):
    _ = current_user
    return sorted_platform_capabilities()


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


@router.get("/{agent_id}/usage/summary", response_model=TenantUsageStatsDTO)
async def get_agent_usage_summary(
    agent_id: int,
    days: int = Query(default=30, ge=1, le=90),
    user_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db, current_user.tenant_id).get_agent_usage_summary_for_actor(
        agent_id=agent_id,
        actor=_actor(current_user),
        days=days,
        user_id=user_id,
    )


@router.get("/{agent_id}/usage/daily", response_model=list[TokenUsageDailyPoint])
async def get_agent_usage_daily(
    agent_id: int,
    days: int = Query(default=30, ge=1, le=90),
    user_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db, current_user.tenant_id).get_agent_usage_daily_for_actor(
        agent_id=agent_id,
        actor=_actor(current_user),
        days=days,
        user_id=user_id,
    )


@router.get("/{agent_id}/usage/events", response_model=TokenUsageEventsResponse)
async def get_agent_usage_events(
    agent_id: int,
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    if page < 1:
        raise ValidationError("page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise ValidationError("page_size must be between 1 and 100")

    period_end = end_time or datetime.now(UTC)
    period_start = start_time or (period_end - timedelta(days=30))

    return await _service(db, current_user.tenant_id).get_agent_usage_events_for_actor(
        agent_id=agent_id,
        actor=_actor(current_user),
        start_time=period_start,
        end_time=period_end,
        page=page,
        page_size=page_size,
        user_id=user_id,
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
