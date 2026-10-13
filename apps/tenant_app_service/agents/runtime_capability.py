"""Build agent capability profiles for chat and downstream delivery (e.g. Slack)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ
from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills
from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
from apps.tenant_app_service.agents.domain import AgentCapabilityProfile


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
    return AgentCapabilityProfile(
        allowed_tool_names=list(allowed_tool_names),
        allowed_skill_names=list(domain.profile.skills),
        allowed_collection_ids=list(domain.profile.knowledge_base_ids),
        allowed_data_source_ids=list(domain.profile.data_source_ids),
        allowed_api_connector_ids=list(domain.profile.api_connector_ids),
    )
