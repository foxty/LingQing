"""Chat service for handling agent interactions and thread management."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    AuthorizationError,
    InternalServiceError,
)
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_pool import get_agent_pool
from apps.tenant_app_service.agents.context import create_thread_id
from apps.tenant_app_service.agents.metrics import session_tracker
from apps.tenant_app_service.chat.adapters import (
    chat_message_to_domain,
    db_artifact_to_domain,
    domain_conversation_to_api,
    domain_message_to_api,
)
from apps.tenant_app_service.chat.domain import ThreadDomain
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.repository import ThreadRepository
from apps.tenant_app_service.chat.schemas import (
    ChatRequest,
    ChatResponse,
    Message,
    SessionStatusResponse,
    SimpleMessage,
)
from apps.tenant_app_service.chat.session_status import resolve_session_status
from apps.tenant_app_service.chat.session_summary_manager import SessionSummaryManager
from apps.tenant_app_service.chat.streaming import ChatStreamingMixin
from apps.tenant_app_service.chat.thread_summary_manager import ThreadSummaryManager
from apps.tenant_app_service.tenant.adapters import db_tenant_to_domain
from apps.tenant_app_service.tenant.domain import TenantDomain
from apps.tenant_app_service.tenant.repository import TenantRepository

MAX_THREADS_PER_USER = 20
DEFAULT_HISTORY_MESSAGE_LIMIT = 1
HITL_CONTINUATION_HISTORY_LIMIT = 12


class ChatService(TenantAwareService, ChatStreamingMixin):
    """Service for handling chat operations and thread management.

    Consolidates both conversation state (checkpointer) and thread metadata (DB).
    All operations are automatically scoped to the tenant context.
    """

    def __init__(self, tenant_id: int, db: AsyncSession):
        """Initialize chat service.

        Args:
            tenant_id: Tenant ID for all operations
            db: Database session for thread management and observability
        """
        super().__init__(tenant_id=tenant_id, db_session=db)
        self.logger = get_logger(ChatService.__name__)
        self.db = db
        self.agent_pool = get_agent_pool()
        self.thread_repo = ThreadRepository(db)
        self.message_repo = MessageRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.artifact_repo = ArtifactRepository(db)

    async def _get_tenant_domain(self) -> TenantDomain:
        """Get tenant domain model for agent runtime context.

        Returns:
            TenantDomain with config
        """
        tenant = await self.tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise AuthorizationError(f"Tenant {self.tenant_id} not found")
        return db_tenant_to_domain(tenant)

    # ============================================================================
    # Thread Management Methods
    # ============================================================================

    async def create_thread(
        self,
        user_id: int,
        agent_id: int,
        title: str | None = None,
        first_message: str | None = None,
    ) -> ThreadDomain:
        """Create a new thread.

        If user already has MAX_THREADS_PER_USER threads, delete the oldest one.

        Args:
            user_id: User ID
            agent_id: Agent ID
            title: Optional thread title
            first_message: Optional first message to auto-generate title from

        Returns:
            Created ThreadDomain
        """
        # Auto-generate title from first message if not provided
        if not title and first_message:
            title = self._extract_title_from_message(first_message)

        # Check thread count and cleanup if needed
        count = await self.thread_repo.count_by_user(self.tenant_id, user_id)
        if count >= MAX_THREADS_PER_USER:
            self.logger.info("User %s has %s threads, deleting oldest to make room", user_id, count)
            await self.thread_repo.delete_oldest_thread(self.tenant_id, user_id)

        # Generate thread ID
        thread_uuid = str(uuid4())
        thread_id = f"{self.tenant_id}_{user_id}_{agent_id}_{thread_uuid}"

        # Create thread
        thread = await self.thread_repo.create_thread(
            thread_id=thread_id,
            tenant_id=self.tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            title=title,
        )

        self.logger.info("Created thread %s for user %s", thread_id, user_id)
        return thread

    async def get_thread(self, thread_id: str) -> ThreadDomain | None:
        """Get thread by ID."""
        return await self.thread_repo.get_by_id(thread_id)

    async def list_user_threads(
        self,
        user_id: int,
        agent_id: int | None = None,
        *,
        actor: ActorContext | None = None,
    ) -> list[ThreadDomain]:
        """List threads the user can still open.

        Threads whose agent the actor can no longer access are omitted.
        Results are ordered by updated_at desc, limited to MAX_THREADS_PER_USER.
        """
        if actor is not None and agent_id is not None:
            await self._require_agent_readable(agent_id, actor)

        threads = await self.thread_repo.list_by_user(
            self.tenant_id, user_id, limit=MAX_THREADS_PER_USER, agent_id=agent_id
        )
        if actor is None or agent_id is not None:
            return threads

        allowed_agent_ids = await self._accessible_agent_ids(actor)
        return [thread for thread in threads if thread.agent_id in allowed_agent_ids]

    async def _require_agent_readable(self, agent_id: int, actor: ActorContext) -> None:
        from apps.shared.domain.types import ABAC_ACTION_READ
        from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
        from apps.tenant_app_service.agent_catalog.services import AgentCatalogService

        if agent_id == SYSTEM_AGENT_ONE_ID:
            return
        catalog = AgentCatalogService(tenant_id=self.tenant_id, db_session=self.db)
        await catalog.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_READ)

    async def _accessible_agent_ids(self, actor: ActorContext) -> set[int]:
        from apps.tenant_app_service.agent_catalog.services import AgentCatalogService

        catalog = AgentCatalogService(tenant_id=self.tenant_id, db_session=self.db)
        agents = await catalog.list_agents_for_actor(actor=actor)
        return {item.id for item in agents}

    async def update_thread_title(self, thread_id: str, title: str) -> ThreadDomain | None:
        """Update thread title."""
        return await self.thread_repo.update_thread(thread_id, title=title)

    async def increment_message_count(self, thread_id: str) -> ThreadDomain | None:
        """Increment message count for a thread."""
        thread = await self.thread_repo.get_by_id(thread_id)
        if not thread:
            return None

        return await self.thread_repo.update_thread(thread_id, message_count=thread.message_count + 1)

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread and clean up associated conversation state.

        This removes both:
        - Thread metadata from database
        - Conversation state from checkpointer
        - Temporary tables associated with the thread

        Args:
            thread_id: Thread ID to delete

        Returns:
            True if deletion was successful
        """
        success = await self.thread_repo.delete_thread(thread_id)
        if success:
            self.logger.info("Deleted thread %s", thread_id)

            try:
                from sqlalchemy import delete

                from apps.shared.db.models import IngressThreadLink

                result = await self.db.execute(
                    delete(IngressThreadLink).where(
                        IngressThreadLink.tenant_id == self.tenant_id,
                        IngressThreadLink.chat_thread_id == thread_id,
                    )
                )
                link_count = result.rowcount or 0
                if link_count > 0:
                    self.logger.info(
                        "Removed %s ingress thread link(s) for deleted thread %s",
                        link_count,
                        thread_id,
                    )
            except Exception:
                self.logger.exception("Failed to clean up ingress thread links for thread %s", thread_id)

            # Clean up temp tables
            try:
                from apps.tenant_app_service.agents.workspace_utils import cleanup_temp_tables_for_thread

                deleted_count = await cleanup_temp_tables_for_thread(self.tenant_id, thread_id)
                if deleted_count > 0:
                    self.logger.info("Cleaned up %s temp tables for thread %s", deleted_count, thread_id)
            except Exception:
                self.logger.exception("Failed to clean up temp tables for thread %s", thread_id)

        return success

    def _extract_title_from_message(self, message: str, max_length: int = 50) -> str:
        """Extract title from first message.

        Args:
            message: Message content
            max_length: Maximum title length

        Returns:
            Extracted title
        """
        title = message.strip()[:max_length]
        if len(message.strip()) > max_length:
            title += "..."
        return title

    def _convert_to_langchain_messages(self, messages: list) -> list:
        """Convert SimpleMessage (from ChatRequest) to LangChain messages.

        Args:
            messages: List of SimpleMessage objects (role='human', content=str)

        Returns:
            List of HumanMessage objects with IDs and timestamps
        """
        return [
            HumanMessage(
                id=str(uuid4()),  # Generate unique ID for deduplication
                content=msg.content,
                additional_kwargs={"timestamp": datetime.now(UTC).isoformat()},
            )
            for msg in messages
        ]

    async def get_session_status(
        self,
        *,
        thread_id: str,
        agent_id: int,
    ) -> SessionStatusResponse:
        """Return durable session status for frontend polling."""
        return await resolve_session_status(
            tenant_id=self.tenant_id,
            db=self.db,
            message_repo=self.message_repo,
            thread_id=thread_id,
            agent_id=agent_id,
        )

    async def run_headless(
        self,
        *,
        user_id: int,
        agent_id: int,
        message: str,
        origin_thread_id: str | None = None,
        task_name: str | None = None,
    ) -> ChatResponse:
        """Run a chat turn on behalf of a user without an HTTP request.

        Used by scheduled agent_run tasks and other background entry points.
        Scheduled runs always reuse origin_thread_id when that thread still exists.
        """
        from apps.tenant_app_service.auth.adapters import db_user_to_domain, domain_user_to_api
        from apps.tenant_app_service.auth.repository import UserRepository
        from apps.tenant_app_service.auth.token import JwtTokenIssuer

        tenant = await self.tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise AuthorizationError(f"Tenant {self.tenant_id} not found")

        user_repo = UserRepository(self.db)
        db_user = await user_repo.get_by_id_and_tenant(user_id, self.tenant_id)
        if not db_user:
            raise AuthorizationError(f"User {user_id} not found in tenant {self.tenant_id}")

        user_dto = domain_user_to_api(db_user_to_domain(db_user), tenant.name)
        access_token = JwtTokenIssuer().issue(
            user_id=user_dto.id,
            username=user_dto.username,
            role=user_dto.role,
            tenant_id=self.tenant_id,
            tenant_name=tenant.name,
        )
        thread_id = await self._resolve_scheduled_thread_id(
            user_id=user_id,
            agent_id=agent_id,
            message=message,
            origin_thread_id=origin_thread_id,
            task_name=task_name,
        )
        request = ChatRequest(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            message=SimpleMessage(role="human", content=message),
            thread_id=thread_id,
        )
        return await self.chat(request, current_user=user_dto, access_token=access_token)

    async def _resolve_scheduled_thread_id(
        self,
        *,
        user_id: int,
        agent_id: int,
        message: str,
        origin_thread_id: str | None,
        task_name: str | None = None,
    ) -> str:
        if origin_thread_id:
            existing = await self.get_thread(origin_thread_id)
            if existing and existing.tenant_id == self.tenant_id and existing.user_id == user_id:
                return existing.id

        title_source = task_name or message
        thread = await self.create_thread(
            user_id=user_id,
            agent_id=agent_id,
            title=title_source[:120],
            first_message=message,
        )
        return thread.id

    # ============================================================================
    # Chat Methods
    # ============================================================================

    async def chat(self, request: ChatRequest, current_user: UserDTO, access_token: str | None = None) -> ChatResponse:
        """Handle non-streaming chat request.

        Frontend sends only the new user message.
        The checkpointer automatically maintains conversation history via thread_id.

        Args:
            request: Chat request with single new message
            current_user: Current authenticated user (for thread isolation and permissions)

        Returns:
            ChatResponse with agent's reply

        Raises:
            HTTPException: If validation or invocation fails
        """
        # Verify request tenant matches service tenant
        if request.tenant_id != self.tenant_id:
            raise AuthorizationError(
                f"Tenant mismatch: request tenant {request.tenant_id} != service tenant {self.tenant_id}"
            )

        agent_id = await self._resolve_agent_id(request)

        await self._cancel_superseded_hitl_if_needed(request)

        session_id = str(uuid4())
        tenant = await self._get_tenant_domain()

        agent_graph, capability_profile = await self._get_agent_graph(agent_id, current_user)
        attachment_scope = None
        if capability_profile is not None:
            attachment_scope = {
                "collections": capability_profile.allowed_collection_ids,
                "data_sources": capability_profile.allowed_data_source_ids,
                "api_connectors": capability_profile.allowed_api_connector_ids,
            }
        self.logger.info(
            "Chat request received tenant=%s agent=%s user_id=%s attachment_scope=%s",
            self.tenant_id,
            agent_id,
            current_user.id,
            attachment_scope,
        )

        # For HITL continuation, keep user message and add continuation signal to resume workflow.
        lc_messages = self._convert_to_langchain_messages([request.message])
        lc_messages = await self._inject_message_attachments(
            lc_messages,
            selected_artifact_ids=request.selected_artifact_ids,
            selected_artifact_id=request.selected_artifact_id,
            current_user=current_user,
        )

        self.logger.debug(f"Converted message for tenant {request.tenant_id}, agent {agent_id}")
        # Invoke agent
        config = None
        result = None

        try:
            config = self._build_runtime_config(
                request=request,
                current_user=current_user,
                agent_id=agent_id,
                agent_name=agent_graph.get_name(),
                session_id=session_id,
                tenant=tenant,
                access_token=access_token,
                capability_profile=capability_profile,
            )

            # Extract runtime context for metrics tracking
            from apps.tenant_app_service.agents.context import extract_runtime_context

            runtime_ctx = extract_runtime_context(config)

            async with session_tracker(runtime_ctx):
                result = await agent_graph.ainvoke(
                    {
                        "messages": lc_messages,
                        "loop_count": 0,
                        "tool_call_counts": {},
                    },
                    config=config,
                )

                # Extract the last assistant message and attach session_id
                from apps.tenant_app_service.agents.message_content import normalize_message_content

                last_message = result["messages"][-1]
                content = normalize_message_content(last_message.content)

                # Attach session_id to the message for metrics linking
                if not last_message.additional_kwargs.get("session_id"):
                    last_message.additional_kwargs["session_id"] = session_id

                self.logger.info(
                    f"Chat request completed successfully - tenant: {self.tenant_id}, agent: {agent_id}, "
                    f"user: {current_user.username}, session: {session_id}"
                )

                effective_thread_id = request.thread_id or create_thread_id(
                    current_user.id, self.tenant_id, agent_id
                )

                return ChatResponse(
                    response=Message(
                        message_id=getattr(last_message, "id", None),
                        role="ai",
                        content=content,
                        agent_id=agent_id,
                        thread_id=effective_thread_id,
                        session_id=session_id,
                    ),
                    agent_id=agent_id,
                    tenant_id=self.tenant_id,
                )

        except Exception as e:
            self.logger.error(
                f"Error invoking agent {agent_id} for tenant {self.tenant_id}: {str(e)}",
                exc_info=True,
            )
            raise InternalServiceError(f"Error invoking agent: {str(e)}")
        finally:
            # Asynchronously create session summary and check thread summary (non-blocking)
            asyncio.create_task(
                self._handle_session_end_async(
                    session_id=session_id,
                    thread_id=request.thread_id,
                )
            )

    async def create_thread_title_if_1st_message(self, content: str, thread_id: str, session_id: str) -> str:
        thread = await self.thread_repo.get_by_id(thread_id)
        if thread.message_count == 0:
            from apps.tenant_app_service.agents.mini_agent import MiniAgentService

            self.logger.info(f"Generating thread title for first message in thread {thread_id}")
            thread_title = "New Thread"
            # update thread title base on first message if title is default
            mini_agent = MiniAgentService(tenant_id=self.tenant_id, db=self.db)
            try:
                thread_title = await mini_agent.common_llm_call(
                    agent_name="ThreadTitleGenerator",
                    user_prompt=content,
                    thread_id=thread_id,
                    session_id=session_id,
                )
            except Exception:
                self.logger.exception("Failed to generate thread title using MiniAgent.")
                thread_title = content[:15] + ("..." if len(content) > 20 else "")
            return thread_title
        else:
            return None

    async def get_conversation_history(
        self,
        agent_id: int,
        current_user: UserDTO,
        thread_id: str,
        session_id: str | None = None,
        session_limit: int = 5,
        before_session_id: str | None = None,
        include_tool_messages: bool | None = None,
    ):
        """Get conversation history (messages) for a thread.

        This loads raw messages from the database (not from checkpointer).

        Args:
            agent_id: Agent ID
            current_user: Current user
            thread_id: Thread ID
            session_limit: Maximum number of sessions to return per page

        Returns:
            Conversation DTO with messages
        """
        self.logger.info(
            "Fetching conversation history - tenant: %s, agent: %s, user: %s, thread_id: %s, "
            "session_id=%s, session_limit=%s, before_session_id=%s, include_tool_messages=%s",
            self.tenant_id,
            agent_id,
            current_user.username,
            thread_id,
            session_id,
            session_limit,
            before_session_id,
            include_tool_messages,
        )

        # Get thread metadata from DB
        thread = await self.thread_repo.get_by_id(thread_id)
        db_messages, has_more, next_before_session_id = await self.message_repo.get_messages_by_session_window(
            thread_id=thread_id,
            agent_id=agent_id,
            session_limit=session_limit,
            before_session_id=before_session_id,
            include_tool_messages=include_tool_messages if include_tool_messages is not None else True,
            session_id=session_id,
        )

        if not db_messages:
            self.logger.info(f"No messages found for thread: {thread_id}")
            return domain_conversation_to_api(
                thread,
                current_user.username,
                next_before_created_at=None,
                next_before_id=None,
                next_before_session_id=None,
                has_more=False,
            )

        next_before_created_at = None
        next_before_id = None
        if db_messages:
            oldest = db_messages[0]
            next_before_created_at = oldest.created_at.isoformat() if oldest.created_at else None
            next_before_id = oldest.id

        # Add DB messages directly to thread (no conversion needed)
        for db_msg in db_messages:
            added = thread.add_message_from_db(db_msg)
            if not added:
                self.logger.debug(f"Message filtered out, type: {db_msg.type}")

        self.logger.info(
            f"Retrieved {len(db_messages)} messages from database for thread: {thread_id} "
            f"({len(thread.messages)} messages in thread after filtering)"
        )

        # Convert domain to DTO before returning
        return domain_conversation_to_api(
            thread,
            current_user.username,
            next_before_created_at=next_before_created_at,
            next_before_id=next_before_id,
            next_before_session_id=next_before_session_id,
            has_more=has_more,
        )

    async def get_tool_call_detail(
        self,
        *,
        thread_id: str,
        tool_call_id: str,
        session_id: str | None = None,
    ) -> Message | None:
        """Get a single tool message detail by tool_call_id."""
        db_msg = await self.message_repo.get_tool_message_by_call_id(
            thread_id=thread_id,
            tool_call_id=tool_call_id,
            session_id=session_id,
        )
        if not db_msg:
            return None

        domain_msg = chat_message_to_domain(db_msg)
        return domain_message_to_api(domain_msg)

    async def _resolve_agent_id(self, request: ChatRequest) -> int:
        """Use the thread's immutable agent when a thread already exists."""
        if not request.thread_id:
            return request.agent_id
        thread = await self.get_thread(request.thread_id)
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
            create_agent_runtime_user_context,
        )

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

        history_message_limit = (
            HITL_CONTINUATION_HISTORY_LIMIT if self._is_hitl_continuation(request) else DEFAULT_HISTORY_MESSAGE_LIMIT
        )

        # Build LangChain configuration
        hitl_resume = (
            {
                "proposal_id": request.hitl_proposal_id,
                "action": request.hitl_action,
            }
            if self._is_hitl_continuation(request)
            else None
        )

        config = {
            "configurable": {
                "thread_id": thread_id,
                "db_session": db_session or self.db,
                "runtime": runtime_ctx.model_dump(),
                "thinking_effort": request.thinking_effort,
                "history_message_limit": history_message_limit,
                # On HITL resume: signals agent_base._load_history to rewrite the stale
                # PENDING ToolMessage, and tool_executor._handle_hitl_gate to use the
                # known proposal_id directly (avoids arg-hash drift from LLM re-generation).
                **(({"hitl_resume": hitl_resume}) if hitl_resume else {}),
            },
            "recursion_limit": 999,  # Safety net, should be higher than MAX_ITERATIONS
        }
        self.logger.debug(
            f"Agent runtime context created - session_id: {session_id}, thread_id: {runtime_ctx.thread_id}, "
            f"user: {runtime_ctx.user.username}, role: {runtime_ctx.user.role}, "
            f"tenant: {runtime_ctx.user.tenant_name}, agent: {agent_name}"
        )

        return config

    async def _handle_session_end_async(
        self,
        session_id: str,
        thread_id: str,
    ) -> None:
        """Handle session end asynchronously.

        Creates session summary and checks if thread summary is needed.
        Works for both streaming and non-streaming modes.
        Statistics (tokens, duration, etc.) are tracked separately by Metrics V3.

        Args:
            session_id: Session ID
            thread_id: Thread ID

        Note:
            Creates its own database session to avoid conflicts with router-level
            session lifecycle. The router session is closed immediately after the
            response is sent, but this background task may still be running.
        """
        try:
            from apps.shared.db.session import app_db_session

            # Background tasks must use their own session: the router-level session
            # is closed as soon as the response is sent, which may happen before
            # this task finishes.  app_db_session() commits on clean exit and rolls
            # back on any exception.
            async with app_db_session() as db:
                # 1. Create session summary + mark messages as summarized, then commit.
                # These two writes must be persisted regardless of whether a thread
                # summary is triggered next.
                session_summary_manager = SessionSummaryManager(db, self.tenant_id)
                session_summary = await session_summary_manager.create_session_summary(
                    session_id=session_id,
                    thread_id=thread_id,
                )
                await db.commit()

                if not session_summary:
                    self.logger.warning(f"Failed to create session summary for session {session_id}")

                # 2. Check and create thread summary if needed.
                # ThreadSummaryManager.create_thread_summary() manages its own
                # commit/rollback internally.
                thread_summary_manager = ThreadSummaryManager(db, self.tenant_id)
                thread_summary = await thread_summary_manager.check_and_create_if_needed(thread_id)

                if thread_summary:
                    self.logger.info(f"Created thread summary v{thread_summary.version} for thread {thread_id}")

        except Exception as e:
            self.logger.error(
                f"Failed to handle session end for session {session_id}: {e}",
                exc_info=True,
            )

    async def _inject_message_attachments(
        self,
        lc_messages: list,
        *,
        selected_artifact_ids: list[int] | None = None,
        selected_artifact_id: int | None = None,
        current_user: UserDTO | None = None,
    ) -> list:
        """Inject @mention artifact context for the agent."""
        ids: list[int] = []
        if selected_artifact_ids:
            ids.extend(selected_artifact_ids)
        elif selected_artifact_id is not None:
            ids.append(selected_artifact_id)
        if not ids:
            return lc_messages
        return await self._inject_selected_artifacts(
            lc_messages,
            ids,
            current_user=current_user,
        )

    async def _inject_selected_artifacts(
        self,
        lc_messages: list,
        artifact_ids: list[int],
        *,
        current_user: UserDTO | None,
    ) -> list:
        """Inject artifact continuity context from artifact record ids (not thread-scoped)."""
        if not artifact_ids or current_user is None:
            return lc_messages

        from apps.shared.artifact.access import require_artifact_record_read

        context_lines = [
            "[Context] The user attached the following artifacts to continue working on:",
        ]
        metadata: list[dict] = []

        for artifact_id in artifact_ids:
            try:
                record = await require_artifact_record_read(
                    db=self.db,
                    tenant_id=self.tenant_id,
                    user_id=current_user.id,
                    user_role=current_user.role,
                    artifact_id=artifact_id,
                )
                artifact = db_artifact_to_domain(record)
                context_lines.append(
                    f"- Type: {artifact.artifact_type}, Title: {artifact.title}, "
                    f"Artifact id: {artifact.id}, Resource id: {artifact.resource_id}, "
                    f"URL: {artifact.url or 'n/a'}"
                )
                metadata.append(
                    {
                        "artifact_id": artifact.id,
                        "artifact_type": artifact.artifact_type,
                        "title": artifact.title or "Untitled",
                        "resource_id": artifact.resource_id,
                    }
                )
            except Exception as exc:
                self.logger.warning(
                    "Skipping inaccessible artifact %s for user %s: %s",
                    artifact_id,
                    current_user.id,
                    exc,
                )
                context_lines.append(f"- artifact id={artifact_id}: not accessible")
                metadata.append(
                    {
                        "artifact_id": artifact_id,
                        "artifact_type": "unknown",
                        "title": f"Artifact #{artifact_id}",
                        "inaccessible": True,
                    }
                )

        context_lines.append(
            "Use the tools appropriate to each artifact type to inspect or update the underlying resource."
        )
        lc_messages.insert(0, SystemMessage(content="\n".join(context_lines)))
        self._stamp_attached_artifacts(lc_messages, metadata)
        return lc_messages

    @staticmethod
    def _stamp_attached_artifacts(lc_messages: list, items: list[dict]) -> None:
        if not items:
            return
        chip_payload = [
            {
                "artifact_id": item["artifact_id"],
                "artifact_type": item.get("artifact_type", "unknown"),
                "title": item.get("title", "Untitled"),
                "resource_type": item.get("artifact_type", "unknown"),
                "resource_id": item["artifact_id"],
            }
            for item in items
        ]
        for msg in reversed(lc_messages):
            if isinstance(msg, HumanMessage):
                kwargs = dict(msg.additional_kwargs or {})
                kwargs["attached_artifacts"] = chip_payload
                msg.additional_kwargs = kwargs
                return

    async def agent_thinking_effort_control_enabled(self, agent_id: int, actor: ActorContext) -> bool:
        """Whether workbench reasoning effort applies to this agent's resolved LLM profile."""
        from apps.shared.infra.llm.thinking import model_supports_thinking
        from apps.shared.llm_providers.service import LLMProviderConfigService
        from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills
        from apps.tenant_app_service.agent_catalog.services import AgentCatalogService

        catalog = AgentCatalogService(tenant_id=self.tenant_id, db_session=self.db)
        assignable_skills = resolve_assignable_skills(tenant_id=self.tenant_id, user_id=actor.user_id)
        agent = await catalog.get_agent_for_actor(
            agent_id=agent_id,
            actor=actor,
            assignable_skills=assignable_skills,
        )
        llm = LLMProviderConfigService(self.tenant_id, self.db)
        await llm.ensure_migrated()
        resolved = await llm.resolve_for_agent(agent.config.model_profile_id, mini=False)
        return model_supports_thinking(resolved)

