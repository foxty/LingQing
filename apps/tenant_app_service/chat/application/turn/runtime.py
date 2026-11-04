"""Chat turn application mixins — composed by ``ChatTurnService``."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.context import create_thread_id
from apps.tenant_app_service.chat.application.threads.thread_service import ThreadService
from apps.tenant_app_service.chat.schemas import ChatRequest
from apps.tenant_app_service.tenant.domain import TenantDomain


class ChatTurnRuntimeMixin:
    async def _resolve_agent_id(self, request: ChatRequest) -> int:
        """Use the thread's immutable agent when a thread already exists."""
        if not request.thread_id:
            return request.agent_id
        thread = await ThreadService(self.tenant_id, self.db).get_thread(request.thread_id)
        if thread is None:
            return request.agent_id
        return thread.agent_id

    async def _get_system_agent_graph(self, agent_id: int):
        """Backward-compatible wrapper for system-agent graph loading."""
        graph, _profile = await self._get_agent_graph(agent_id, current_user=None)
        return graph

    async def _get_agent_graph(self, agent_id: int, current_user: UserDTO | None):
        """Load a system or custom agent graph plus its runtime capability profile."""
        from apps.shared.domain.actor import ActorContext
        from apps.shared.domain.types import ABAC_ACTION_READ
        from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
        from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
        from apps.tenant_app_service.agents.system_agent_config import load_yaml_agent_config

        if agent_id <= SYSTEM_AGENT_ONE_ID or agent_id < 0:
            self.logger.info("Using system agent: %s", agent_id)
            graph = await self.agent_pool.get_or_create_agent(load_yaml_agent_config(agent_id))
            return graph, None

        if current_user is None:
            raise AuthorizationError("Custom agents require an authenticated user")

        from apps.shared.authz.ta_permissions import TenantAppPermissions
        from apps.shared.authz.ta_rbac import role_has_permission

        if not await role_has_permission(
            db=self.db,
            tenant_id=current_user.tenant_id,
            role_key=current_user.role,
            permission=TenantAppPermissions.AGENTS_READ,
        ):
            raise AuthorizationError("无权访问该智能体")

        from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills

        catalog = AgentCatalogService(tenant_id=self.tenant_id, db_session=self.db)
        actor = ActorContext(tenant_id=current_user.tenant_id, user_id=current_user.id, user_role=current_user.role)
        domain = await catalog.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_READ)

        from apps.tenant_app_service.agents.custom_agent_loaded_config import (
            build_custom_agent_loaded_config,
            runtime_defaults_from_system_agent,
        )
        from apps.tenant_app_service.agents.system_agent_config import get_config_loader

        loader = get_config_loader()
        yaml_one = loader.get_system_agent_config(SYSTEM_AGENT_ONE_ID, materialize=False) or {}
        assignable_skills = resolve_assignable_skills(
            tenant_id=current_user.tenant_id, user_id=current_user.id
        )
        derived_tool_names = catalog.derived_tool_names(
            domain.profile,
            assignable_skills=assignable_skills,
        )
        preloaded = build_custom_agent_loaded_config(
            domain=domain,
            derived_tool_names=derived_tool_names,
            loader=loader,
            runtime_defaults=runtime_defaults_from_system_agent(yaml_one),
        )

        revision = domain.updated_at.isoformat() if domain.updated_at else "0"
        graph = await self.agent_pool.get_or_create_agent(
            preloaded,
            cache_revision=revision,
        )
        from apps.tenant_app_service.agents.runtime_capability import build_agent_capability_profile

        profile = await build_agent_capability_profile(
            self.db,
            tenant_id=self.tenant_id,
            actor=actor,
            agent_id=agent_id,
            assignable_skills=assignable_skills,
        )
        return graph, profile

    def _build_runtime_config(
        self,
        tenant: TenantDomain,
        current_user: UserDTO,
        request: ChatRequest,
        agent_id: int,
        agent_name: str,
        session_id: str,
        access_token: str | None = None,
        db_session: AsyncSession | None = None,
        capability_profile=None,
        run_id: str | None = None,
        trigger_message_id: str | None = None,
        invoke_index: int = 0,
        *,
        skip_load_history: bool = False,
        hitl_proposal_id: str | None = None,
        pin_graph_db_session: bool = True,
    ) -> dict:
        """Build configuration for agent invocation.

        Args:
            tenant: Tenant domain object
            current_user: Current authenticated user
            request: Chat request
            agent_id: Agent ID
            agent_name: Agent name
            session_id: Unique session ID for this invocation

        Returns:
            Configuration dictionary with runtime context
        """
        from apps.tenant_app_service.agents.context import (
            create_agent_runtime_context,
            create_agent_runtime_tenant_context,
        )
        from apps.tenant_app_service.chat.runtime_context_builders import create_agent_runtime_user_context

        thread_id = request.thread_id
        if not thread_id:
            thread_id = create_thread_id(current_user.id, self.tenant_id, agent_id)
        user_ctx = create_agent_runtime_user_context(current_user, access_token=access_token)
        tenant_config = tenant.config.to_dict() if tenant and tenant.config else {}
        tenant_ctx = create_agent_runtime_tenant_context(
            tenant_id=self.tenant_id,
            tenant_name=current_user.tenant_name,
            config=tenant_config,
        )

        runtime_ctx = create_agent_runtime_context(
            tenant_context=tenant_ctx,
            user_context=user_ctx,
            agent_id=agent_id,
            agent_name=agent_name,
            thread_id=thread_id,
            session_id=session_id,
            capability_profile=capability_profile,
        )

        checkpoint_thread_id = run_id or thread_id

        pinned_db = (db_session or self.db) if pin_graph_db_session else None
        config = {
            "configurable": {
                "thread_id": checkpoint_thread_id,
                "db_session": pinned_db,
                "runtime": runtime_ctx.model_dump(),
                "thinking_effort": request.thinking_effort,
                **({"run_id": run_id} if run_id else {}),
                **({"trigger_message_id": trigger_message_id} if trigger_message_id else {}),
                "invoke_index": invoke_index,
                **({"skip_load_history": True} if skip_load_history else {}),
                **({"hitl_proposal_id": hitl_proposal_id} if hitl_proposal_id else {}),
            },
            "recursion_limit": 999,  # Safety net, should be higher than MAX_ITERATIONS
        }
        if run_id:
            from apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter import (
                chat_agent_run_port_for_run,
            )

            run_port = chat_agent_run_port_for_run(
                tenant_id=self.tenant_id,
                agent_id=agent_id,
                run_id=run_id,
            )
            config["configurable"]["agent_run_port"] = run_port
        self.logger.debug(
            f"Agent runtime context created - session_id: {session_id}, thread_id: {runtime_ctx.thread_id}, "
            f"user: {runtime_ctx.user.username}, role: {runtime_ctx.user.role}, "
            f"tenant: {runtime_ctx.user.tenant_name}, agent: {agent_name}"
        )

        return config
