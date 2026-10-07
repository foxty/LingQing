"""Application service for custom agent catalog."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.authz_query_builder import build_unified_resource_filter, evaluate_resource_action
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.models import (
    ApiConnector,
    DataSource,
    DocumentCollection,
)
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_AGENT,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
    AuthzAction,
)
from apps.shared.llm_providers.service import LLMProviderConfigService
from apps.shared.observability.dtos import TenantUsageStatsDTO
from apps.shared.observability.service import ObservabilityService
from apps.tenant_app_service.tenant.schemas import TokenUsageDailyPoint, TokenUsageEventsResponse
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_catalog.adapters import db_agent_to_custom
from apps.tenant_app_service.agent_catalog.domain import (
    PERSONAL_SKILL_SCOPE,
    SYSTEM_AGENT_ONE_ID,
    SYSTEM_AGENT_ONE_NAME,
    AgentCapabilityProfile,
    AssignableSkill,
    CustomAgent,
    derive_tool_names,
)
from apps.tenant_app_service.agent_catalog.dtos import (
    AgentCapabilityConfigDTO,
    AgentCreateRequest,
    AgentResponse,
    AgentUpdateRequest,
)
from apps.tenant_app_service.agent_catalog.repository import AgentCatalogRepository
from apps.tenant_app_service.agents.system_agent_config import TOOL_REGISTRY, get_config_loader

logger = get_logger(__name__)


class AgentCatalogService(TenantAwareService):
    def __init__(self, tenant_id: int, db_session: AsyncSession):
        super().__init__(tenant_id, db_session=db_session)
        self._repo = AgentCatalogRepository(db_session)

    async def has_agents_manage_permission(self, *, actor: ActorContext) -> bool:
        return await role_has_permission(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.AGENTS_MANAGE,
        )

    async def list_agents_for_actor(
        self,
        *,
        actor: ActorContext,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> list[AgentResponse]:
        has_manage = await self.has_agents_manage_permission(actor=actor)
        scope = await build_unified_resource_filter(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_AGENT,
            action=ABAC_ACTION_READ,
            resource_model=self._repo.model,
            has_manage_permission=has_manage,
        )
        items = [self._system_agent_response(actor=actor)]
        if scope.deny_all:
            return items
        records = await self._repo.list_for_tenant(
            self.tenant_id,
            scope_clause=None if scope.allow_all else scope.clause,
        )
        for record in records:
            domain = db_agent_to_custom(record)
            items.append(await self._to_response(domain, actor=actor, assignable_skills=assignable_skills))
        return items

    async def get_agent_for_actor(
        self,
        *,
        agent_id: int,
        actor: ActorContext,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> AgentResponse:
        if agent_id == SYSTEM_AGENT_ONE_ID:
            return self._system_agent_response(actor=actor)
        domain = await self.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_READ)
        return await self._to_response(domain, actor=actor, assignable_skills=assignable_skills)

    def _observability(self) -> ObservabilityService:
        return ObservabilityService.create(self.db_session, self.tenant_id)

    @staticmethod
    def _usage_period(days: int) -> tuple[datetime, datetime]:
        period_end = datetime.now(UTC)
        return period_end - timedelta(days=days), period_end

    async def _ensure_agent_usage_access(self, *, agent_id: int, actor: ActorContext) -> None:
        if agent_id != SYSTEM_AGENT_ONE_ID:
            await self.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_READ)

    async def get_agent_usage_summary_for_actor(
        self,
        *,
        agent_id: int,
        actor: ActorContext,
        days: int,
        user_id: int | None = None,
    ) -> TenantUsageStatsDTO:
        await self._ensure_agent_usage_access(agent_id=agent_id, actor=actor)
        period_start, period_end = self._usage_period(days)
        return await self._observability().get_agent_usage_stats(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            start_time=period_start,
            end_time=period_end,
            user_id=user_id,
        )

    async def get_agent_usage_daily_for_actor(
        self,
        *,
        agent_id: int,
        actor: ActorContext,
        days: int,
        user_id: int | None = None,
    ) -> list[TokenUsageDailyPoint]:
        await self._ensure_agent_usage_access(agent_id=agent_id, actor=actor)
        period_start, period_end = self._usage_period(days)
        rows = await self._observability().get_tenant_token_daily_usage(
            tenant_id=self.tenant_id,
            start_time=period_start,
            end_time=period_end,
            agent_id=agent_id,
            user_id=user_id,
        )
        return [TokenUsageDailyPoint(**row) for row in rows]

    async def get_agent_usage_events_for_actor(
        self,
        *,
        agent_id: int,
        actor: ActorContext,
        start_time: datetime,
        end_time: datetime,
        page: int,
        page_size: int,
        user_id: int | None = None,
    ) -> TokenUsageEventsResponse:
        await self._ensure_agent_usage_access(agent_id=agent_id, actor=actor)
        total, rows = await self._observability().get_tenant_token_events(
            tenant_id=self.tenant_id,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
            user_id=user_id,
            agent_id=agent_id,
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return TokenUsageEventsResponse(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            rows=rows,
        )

    async def require_agent_access(
        self,
        *,
        agent_id: int,
        actor: ActorContext,
        action: AuthzAction,
    ) -> CustomAgent:
        if agent_id == SYSTEM_AGENT_ONE_ID:
            if action != ABAC_ACTION_READ:
                raise AuthorizationError("System agents are read-only")
            raise ResourceNotFoundError("System agent is not a catalog record")

        record = await self._repo.get_by_id_and_tenant(agent_id, self.tenant_id)
        if record is None:
            raise ResourceNotFoundError(f"Agent {agent_id} not found")
        domain = db_agent_to_custom(record)
        has_manage = await self.has_agents_manage_permission(actor=actor)
        allowed = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_AGENT,
            resource_id=domain.id,
            resource_owner_id=domain.owner_id,
            action=action,
            has_manage_permission=has_manage,
        )
        if not allowed:
            raise AuthorizationError("无权访问该智能体")
        return domain

    async def create_agent(
        self,
        *,
        payload: AgentCreateRequest,
        actor: ActorContext,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> AgentResponse:
        existing = await self._repo.get_by_name(self.tenant_id, payload.name.strip())
        if existing:
            raise DuplicateResourceError(f"Agent '{payload.name}' already exists")

        profile = AgentCapabilityProfile.from_config(payload.config.model_dump())
        await self._validate_profile(profile, actor=actor, assignable_skills=assignable_skills)
        profile.default_tools = self.derived_tool_names(profile, assignable_skills=assignable_skills)

        record = await self._repo.create(
            self._repo.model(
                tenant_id=self.tenant_id,
                owner_id=actor.user_id,
                name=payload.name.strip(),
                description=payload.description,
                system_prompt=payload.system_prompt,
                config=profile.to_config(),
                tags=payload.tags or [],
                example_questions=payload.example_questions or [],
                status="active",
            )
        )
        logger.info("Created custom agent id=%s tenant=%s", record.id, self.tenant_id)
        return await self._to_response(
            db_agent_to_custom(record), actor=actor, assignable_skills=assignable_skills
        )

    async def update_agent(
        self,
        *,
        agent_id: int,
        payload: AgentUpdateRequest,
        actor: ActorContext,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> AgentResponse:
        domain = await self.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_WRITE)
        record = await self._repo.get_by_id_and_tenant(agent_id, self.tenant_id)
        if record is None:
            raise ResourceNotFoundError(f"Agent {agent_id} not found")

        if payload.name and payload.name.strip() != domain.name:
            existing = await self._repo.get_by_name(self.tenant_id, payload.name.strip())
            if existing and existing.id != agent_id:
                raise DuplicateResourceError(f"Agent '{payload.name}' already exists")
            record.name = payload.name.strip()
        if payload.description is not None:
            record.description = payload.description
        if payload.system_prompt is not None:
            record.system_prompt = payload.system_prompt
        if payload.tags is not None:
            record.tags = payload.tags
        if payload.example_questions is not None:
            record.example_questions = payload.example_questions
        if payload.status is not None:
            record.status = payload.status
        if payload.config is not None:
            profile = AgentCapabilityProfile.from_config(payload.config.model_dump())
            await self._validate_profile(profile, actor=actor, assignable_skills=assignable_skills)
            profile.default_tools = self.derived_tool_names(profile, assignable_skills=assignable_skills)
            record.config = profile.to_config()

        record.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        return await self._to_response(
            db_agent_to_custom(record), actor=actor, assignable_skills=assignable_skills
        )

    async def delete_agent(self, *, agent_id: int, actor: ActorContext) -> None:
        await self.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_WRITE)
        deleted = await self._repo.delete_by_id(agent_id)
        if not deleted:
            raise ResourceNotFoundError(f"Agent {agent_id} not found")

    def get_system_agent_template(self) -> AgentResponse:
        return self._system_agent_response(actor=None)

    def derived_tool_names(
        self,
        profile: AgentCapabilityProfile,
        *,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> list[str]:
        _ = assignable_skills
        names = derive_tool_names(
            skills=profile.skills,
            knowledge_base_ids=profile.knowledge_base_ids,
            data_source_ids=profile.data_source_ids,
            api_connector_ids=profile.api_connector_ids,
            platform_capabilities=profile.platform_capabilities,
        )
        return [name for name in names if name in TOOL_REGISTRY]

    def allowed_runtime_tool_names(
        self,
        profile: AgentCapabilityProfile,
        *,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> list[str]:
        """Default tools plus tools declared on assigned skills (available after load)."""
        names = self.derived_tool_names(profile, assignable_skills=assignable_skills)
        seen = set(names)
        by_name = {skill.name: skill for skill in assignable_skills or []}
        for skill_name in profile.skills:
            skill = by_name.get(skill_name)
            if skill is None:
                continue
            for tool_name in skill.tools:
                if tool_name in TOOL_REGISTRY and tool_name not in seen:
                    seen.add(tool_name)
                    names.append(tool_name)
        return names

    async def _validate_profile(
        self,
        profile: AgentCapabilityProfile,
        *,
        actor: ActorContext,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> None:
        by_name = {skill.name: skill for skill in assignable_skills or []}
        for skill_name in profile.skills:
            skill = by_name.get(skill_name)
            if skill is None:
                raise ValidationError(f"Skill '{skill_name}' is not available")
            if skill.scope == PERSONAL_SKILL_SCOPE:
                raise ValidationError(f"Personal skill '{skill_name}' cannot be assigned to a shareable agent")

        await self._require_readable_ids(
            actor=actor,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_ids=profile.knowledge_base_ids,
            model=DocumentCollection,
        )
        await self._require_readable_ids(
            actor=actor,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_ids=profile.data_source_ids,
            model=DataSource,
        )
        await self._require_readable_ids(
            actor=actor,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_ids=profile.api_connector_ids,
            model=ApiConnector,
        )
        if profile.model_profile_id is not None:
            await LLMProviderConfigService(self.tenant_id, self.db_session).validate_agent_model_profile(
                profile.model_profile_id
            )

    async def _require_readable_ids(
        self,
        *,
        actor: ActorContext,
        resource_type: str,
        resource_ids: list[int],
        model,
    ) -> None:
        manage_perm = {
            RESOURCE_TYPE_DOCUMENT_COLLECTION: TenantAppPermissions.DOCUMENTS_MANAGE,
            RESOURCE_TYPE_DATA_SOURCE: TenantAppPermissions.DATA_SOURCES_MANAGE,
            RESOURCE_TYPE_API_CONNECTOR: TenantAppPermissions.API_CONNECTORS_MANAGE,
        }[resource_type]
        has_manage = await role_has_permission(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=manage_perm,
        )
        for resource_id in resource_ids:
            owner_id = await self.db_session.scalar(
                select(model.owner_id).where(model.tenant_id == self.tenant_id, model.id == resource_id)
            )
            if owner_id is None:
                raise ValidationError(f"{resource_type} {resource_id} not found")
            allowed = await evaluate_resource_action(
                db_session=self.db_session,
                tenant_id=self.tenant_id,
                user_id=actor.user_id,
                user_role=actor.user_role,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_owner_id=owner_id,
                action=ABAC_ACTION_READ,
                has_manage_permission=has_manage,
            )
            if not allowed:
                raise AuthorizationError(f"Cannot assign {resource_type} {resource_id}")

    async def _to_response(
        self,
        domain: CustomAgent,
        *,
        actor: ActorContext,
        assignable_skills: list[AssignableSkill] | None = None,
    ) -> AgentResponse:
        has_manage = await self.has_agents_manage_permission(actor=actor)
        can_write = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_AGENT,
            resource_id=domain.id,
            resource_owner_id=domain.owner_id,
            action=ABAC_ACTION_WRITE,
            has_manage_permission=has_manage,
        )
        return AgentResponse(
            id=domain.id,
            name=domain.name,
            description=domain.description,
            system_prompt=domain.system_prompt,
            config=AgentCapabilityConfigDTO(
                **{
                    **domain.profile.to_config(),
                    "default_tools": self.derived_tool_names(
                        domain.profile, assignable_skills=assignable_skills
                    ),
                }
            ),
            tags=domain.tags,
            example_questions=domain.example_questions,
            status=domain.status,
            owner_id=domain.owner_id,
            is_system=False,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            can_write=can_write,
            can_manage=has_manage or domain.owner_id == actor.user_id,
        )

    def _system_agent_response(self, *, actor: ActorContext | None) -> AgentResponse:
        yaml_config = get_config_loader().get_system_agent_config(SYSTEM_AGENT_ONE_ID) or {}
        tool_names = [
            item.get("name")
            for item in yaml_config.get("default_tools", [])
            if isinstance(item, dict) and item.get("name")
        ]
        return AgentResponse(
            id=SYSTEM_AGENT_ONE_ID,
            name=yaml_config.get("name") or SYSTEM_AGENT_ONE_NAME,
            description=yaml_config.get("description"),
            system_prompt=yaml_config.get("system_prompt") or "",
            config=AgentCapabilityConfigDTO(default_tools=tool_names),
            tags=list(yaml_config.get("tags") or []),
            example_questions=list(yaml_config.get("example_questions") or []),
            status="active",
            owner_id=None,
            is_system=True,
            can_write=False,
            can_manage=False,
        )
