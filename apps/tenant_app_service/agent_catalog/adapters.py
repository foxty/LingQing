"""Boundary adapters for the custom agent catalog."""

from apps.shared.db.models import Agent
from apps.tenant_app_service.agent_catalog.domain import AgentCapabilityProfile, AssignableSkill, CustomAgent
from apps.tenant_app_service.agent_catalog.dtos import AgentCapabilityConfigDTO
from apps.tenant_app_service.agents.custom_agent_loaded_config import resolved_max_loop_iterations
from apps.tenant_app_service.agents.system_agent_config import get_config_loader
from apps.tenant_app_service.skills.domain import SkillType
from apps.tenant_app_service.skills.resolution import get_default_skill_resolver


def effective_max_loop_iterations(profile: AgentCapabilityProfile | None = None) -> int:
    stored = profile.max_loop_iterations if profile is not None else None
    return resolved_max_loop_iterations(stored, get_config_loader())


def normalize_max_loop_for_storage(value: int | None) -> int | None:
    if value is None:
        return None
    if value == effective_max_loop_iterations(None):
        return None
    return value


def capability_config_dto_for_response(
    profile: AgentCapabilityProfile,
    *,
    default_tools: list[str],
) -> AgentCapabilityConfigDTO:
    payload = {
        **profile.to_config(),
        "default_tools": default_tools,
        "max_loop_iterations": effective_max_loop_iterations(profile),
    }
    return AgentCapabilityConfigDTO(**payload)


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
