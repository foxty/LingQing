"""Boundary adapters for the custom agent catalog."""

from apps.shared.db.models import Agent
from apps.tenant_app_service.agent_catalog.domain import AgentCapabilityProfile, AssignableSkill, CustomAgent
from apps.tenant_app_service.skills.domain import SkillType
from apps.tenant_app_service.skills.resolution import get_default_skill_resolver


def db_agent_to_custom(record: Agent) -> CustomAgent:
    return CustomAgent(
        id=record.id,
        tenant_id=record.tenant_id,
        owner_id=record.owner_id,
        name=record.name,
        description=record.description,
        system_prompt=record.system_prompt,
        profile=AgentCapabilityProfile.from_config(record.config),
        tags=list(record.tags or []),
        example_questions=list(record.example_questions or []),
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def resolve_assignable_skills(*, tenant_id: int, user_id: int) -> list[AssignableSkill]:
    resolved = get_default_skill_resolver().resolve(tenant_id=tenant_id, user_id=user_id)
    return [
        AssignableSkill(
            name=name,
            description=skill.description or "",
            scope=skill.scope.value if skill.scope else SkillType.BUILTIN.value,
            tools=tuple(tool.name for tool in skill.tools if getattr(tool, "name", None)),
        )
        for name, skill in resolved.items()
    ]
