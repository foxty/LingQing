"""Thread metadata, history, and read-side chat APIs."""

from uuid import uuid4

from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.adapters import (
    chat_message_to_domain,
    domain_conversation_to_api,
    domain_message_to_api,
)
from apps.tenant_app_service.chat.domain import ThreadDomain
from apps.tenant_app_service.chat.schemas import Message, SessionStatusResponse
from apps.tenant_app_service.chat.service_base import MAX_THREADS_PER_USER, ChatServiceBase
from apps.tenant_app_service.chat.session_status import resolve_session_status


class ThreadService(ChatServiceBase):
    """Thread CRUD, message history, session status — no agent invocation."""

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

    async def agent_thinking_effort_control(self, agent_id: int, actor: ActorContext) -> dict[str, object]:
        """Workbench thinking control from the agent model profile DB snapshot."""
        from apps.shared.infra.llm.thinking import list_thinking_effort_options, model_supports_thinking
        from apps.shared.llm_providers.reasoning_options import default_thinking_effort_value
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
        resolved = await llm.resolve_for_agent(agent.config.model_profile_id, mini=False)
        options = list_thinking_effort_options(resolved)
        enabled = model_supports_thinking(resolved)
        return {
            "enabled": enabled,
            "options": options,
            "default_value": default_thinking_effort_value(options) if options else "",
            "model_id": resolved.model_id,
            "profile_name": resolved.profile_name,
        }
