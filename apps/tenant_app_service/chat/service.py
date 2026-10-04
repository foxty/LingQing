"""Chat service for handling agent interactions and thread management."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.context_resource.domain import ContextResourceItem, ContextResourceKey
from apps.shared.context_resource.service import ContextResourceSearchService
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
    ContextResourceRef,
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
        self.logger.info(
            f"Chat request received - tenant: {self.tenant_id}, agent: {agent_id}, "
            f"user: {current_user.username} (id: {current_user.id})"
        )

        await self._cancel_superseded_hitl_if_needed(request)

        session_id = str(uuid4())
        tenant = await self._get_tenant_domain()

        agent_graph, capability_profile = await self._get_agent_graph(agent_id, current_user)

        # For HITL continuation, keep user message and add continuation signal to resume workflow.
        lc_messages = self._convert_to_langchain_messages([request.message])
        lc_messages = await self._inject_selected_context_resources(
            lc_messages,
            request.selected_resource_ids,
            thread_id=request.thread_id,
            selected_artifact_id=request.selected_artifact_id,
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
        from apps.tenant_app_service.agents.domain import AgentCapabilityProfile
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

        yaml_one = load_yaml_agent_config(SYSTEM_AGENT_ONE_ID)
        one_tools = {
            item.get("name"): item
            for item in yaml_one.get("default_tools", [])
            if isinstance(item, dict) and item.get("name")
        }
        assignable_skills = resolve_assignable_skills(
            tenant_id=current_user.tenant_id, user_id=current_user.id
        )
        default_tool_names = catalog.derived_tool_names(
            domain.profile,
            assignable_skills=assignable_skills,
        )
        allowed_tool_names = catalog.allowed_runtime_tool_names(
            domain.profile,
            assignable_skills=assignable_skills,
        )
        default_tools = [one_tools.get(name, {"name": name}) for name in default_tool_names]
        preloaded = {
            **yaml_one,
            "agent_id": domain.id,
            "name": domain.name,
            "system_prompt": domain.system_prompt,
            "default_tools": default_tools,
            "example_questions": domain.example_questions,
        }
        if domain.profile.model_profile_id is not None:
            preloaded["model_profile_id"] = domain.profile.model_profile_id

        revision = domain.updated_at.isoformat() if domain.updated_at else "0"
        graph = await self.agent_pool.get_or_create_agent(
            preloaded,
            cache_revision=revision,
        )
        from apps.shared.authz.delegation import has_agent_delegation

        profile = AgentCapabilityProfile(
            allowed_tool_names=list(allowed_tool_names),
            allowed_skill_names=list(domain.profile.skills),
            allowed_collection_ids=list(domain.profile.knowledge_base_ids),
            allowed_data_source_ids=list(domain.profile.data_source_ids),
            allowed_api_connector_ids=list(domain.profile.api_connector_ids),
            delegate=await has_agent_delegation(
                self.db,
                tenant_id=self.tenant_id,
                agent_id=domain.id,
                user_id=current_user.id,
                owner_id=domain.owner_id,
            ),
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

    async def _inject_selected_context_resources(
        self,
        lc_messages: list,
        resource_refs: list[ContextResourceRef] | None,
        *,
        thread_id: str | None,
        selected_artifact_id: int | None,
    ) -> list:
        """Inject @mention context for the agent and persist display metadata on the human message."""
        if resource_refs:
            items = await self._resolve_context_resource_items(resource_refs)
            context_msg = self._build_context_resources_system_message(items)
            if context_msg:
                lc_messages.insert(0, context_msg)
            self._stamp_human_message_context_resources(lc_messages, items)
            return lc_messages

        if selected_artifact_id and thread_id:
            context_msg = await self._prepare_artifact_context_message(thread_id, selected_artifact_id)
            if context_msg:
                lc_messages.insert(0, context_msg)

        return lc_messages

    @staticmethod
    def _stamp_human_message_context_resources(
        lc_messages: list,
        items: list[ContextResourceItem],
    ) -> None:
        """Attach resolved context resources to the latest human message for history display."""
        if not items:
            return

        summaries = [item.to_metadata_dict() for item in items]
        for msg in reversed(lc_messages):
            if isinstance(msg, HumanMessage):
                kwargs = dict(msg.additional_kwargs or {})
                kwargs["context_resources"] = summaries
                msg.additional_kwargs = kwargs
                return

    async def _resolve_context_resource_items(
        self, resource_refs: list[ContextResourceRef]
    ) -> list[ContextResourceItem]:
        """Resolve @mention refs via shared context resource service."""
        service = ContextResourceSearchService(self.tenant_id, self.db)
        keys = [
            ContextResourceKey(resource_type=ref.resource_type, resource_id=ref.resource_id)
            for ref in resource_refs
        ]
        return await service.resolve_by_refs(keys)

    def _build_context_resources_system_message(
        self, items: list[ContextResourceItem]
    ) -> SystemMessage | None:
        """Build a SystemMessage summarising @mention-selected resources for the agent."""
        if not items:
            return None

        context_lines = [
            "[Context] The user has attached the following resources to this message:",
        ]

        for item in items:
            if item.resource_type == "asset" and item.subtitle and item.subtitle != "not found":
                context_lines.append(
                    f"- Type: asset, Title: {item.title}, Data Source: {item.subtitle}"
                )
            elif item.subtitle == "not found":
                context_lines.append(f"- {item.resource_type} (id={item.resource_id}): not found")
            else:
                context_lines.append(f"- Type: {item.resource_type}, Title: {item.title}")

        context_lines.append(
            "Please use these resources as context when answering the user's question."
        )
        return SystemMessage(content="\n".join(context_lines))

    async def _prepare_context_resources_message(
        self, resource_refs: list[ContextResourceRef]
    ) -> SystemMessage | None:
        """Build a SystemMessage summarising all @mention-selected resources."""
        try:
            items = await self._resolve_context_resource_items(resource_refs)
            self.logger.info(f"Injecting {len(items)} context resource(s) into chat")
            return self._build_context_resources_system_message(items)
        except Exception as e:
            self.logger.error(
                f"Failed to prepare context resources message: {e}",
                exc_info=True,
            )
            return None

    async def _prepare_artifact_context_message(self, thread_id: str, artifact_id: int) -> SystemMessage | None:
        try:
            artifact_model = await self.artifact_repo.get_by_id(artifact_id)
            if not artifact_model or artifact_model.tenant_id != self.tenant_id:
                self.logger.warning(f"Artifact {artifact_id} not found or inaccessible for thread {thread_id}")
                return None

            artifact = db_artifact_to_domain(artifact_model)

            context_text = artifact.generate_context_message()

            self.logger.info(f"Injecting artifact context: {artifact_id} - {artifact.title}")
            return SystemMessage(content=context_text)

        except Exception as e:
            self.logger.error(f"Failed to prepare artifact context message: {e}", exc_info=True)
            return None
