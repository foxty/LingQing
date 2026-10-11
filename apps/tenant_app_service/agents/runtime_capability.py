"""Build agent capability profiles for chat and downstream delivery (e.g. Slack)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.delegation import has_agent_delegation
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills
from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
from apps.tenant_app_service.agents.context import delegated_collection_ids
from apps.tenant_app_service.agents.domain import AgentCapabilityProfile

logger = get_logger(__name__)


async def build_agent_capability_profile(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor: ActorContext,
    agent_id: int,
    assignable_skills: list | None = None,
) -> AgentCapabilityProfile | None:
    """Runtime profile for a custom agent, or ``None`` for system agents."""
    if agent_id <= SYSTEM_AGENT_ONE_ID or agent_id < 0:
        return None

    catalog = AgentCatalogService(tenant_id=tenant_id, db_session=db)
    domain = await catalog.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_READ)

    skills = assignable_skills
    if skills is None:
        skills = resolve_assignable_skills(tenant_id=tenant_id, user_id=actor.user_id)

    allowed_tool_names = catalog.allowed_runtime_tool_names(domain.profile, assignable_skills=skills)
    delegate = await has_agent_delegation(
        db,
        tenant_id=tenant_id,
        agent_id=domain.id,
        user_id=actor.user_id,
        owner_id=domain.owner_id,
    )
    return AgentCapabilityProfile(
        allowed_tool_names=list(allowed_tool_names),
        allowed_skill_names=list(domain.profile.skills),
        allowed_collection_ids=list(domain.profile.knowledge_base_ids),
        allowed_data_source_ids=list(domain.profile.data_source_ids),
        allowed_api_connector_ids=list(domain.profile.api_connector_ids),
        delegate=delegate,
    )


async def resolve_delegated_collection_ids(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor: ActorContext,
    agent_id: int | None,
) -> list[int] | None:
    """Collection IDs readable via agent datascope for this actor (same rules as chat tools)."""
    if agent_id is None or agent_id <= SYSTEM_AGENT_ONE_ID or agent_id < 0:
        return None

    try:
        profile = await build_agent_capability_profile(
            db,
            tenant_id=tenant_id,
            actor=actor,
            agent_id=agent_id,
        )
    except (AuthorizationError, ResourceNotFoundError) as exc:
        logger.debug(
            "Skipping delegated collection ids for agent %s tenant %s: %s",
            agent_id,
            tenant_id,
            exc,
        )
        return None

    return delegated_collection_ids(profile)
