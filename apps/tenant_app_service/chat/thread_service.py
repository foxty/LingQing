"""Thread metadata, history, and read-side chat APIs (single DB session).

**Layer:** Session-scoped service — CRUD, history, tool detail, session status delegate.
**Must not:** LangGraph invoke or multi-session turn orchestration (see ``application/``).
"""

from uuid import uuid4

from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.adapters import (
    chat_message_to_domain,
    domain_message_to_api,
)
from apps.tenant_app_service.chat.agent_run_domain import AgentRunDomain
from apps.tenant_app_service.chat.domain import ThreadDomain
from apps.tenant_app_service.chat.schemas import ActiveRunResponse, ConversationHistoryResponse, Message
from apps.tenant_app_service.chat.service_base import MAX_THREADS_PER_USER, ChatServiceBase
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService


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

    async def get_active_run(
        self,
        *,
        thread_id: str,
        agent_id: int,
    ) -> ActiveRunResponse:
        """Return active agent run snapshot for frontend polling."""
        return await ThreadRunService(self.db, self.tenant_id).get_active_run(
            thread_id=thread_id,
            agent_id=agent_id,
            repair=True,
        )

    async def get_main_timeline_messages(self, thread: ThreadDomain) -> list[Message]:
        """Trigger-anchored main timeline as API messages (human + promoted AI)."""
        from apps.tenant_app_service.chat.history_adapters import main_timeline_rows_to_api_messages

        run_service = ThreadRunService(self.db, self.tenant_id)
        timeline = await run_service.get_timeline(thread.id)
        return main_timeline_rows_to_api_messages(
            timeline,
            thread_id=thread.id,
            default_agent_id=thread.agent_id,
        )

    async def list_runs_for_trigger(
        self,
        thread_id: str,
        trigger_message_id: str,
    ) -> list[AgentRunDomain]:
        """Agent runs spawned from one human message on the main timeline."""
        run_service = ThreadRunService(self.db, self.tenant_id)
        return await run_service.list_runs_for_trigger(thread_id, trigger_message_id)

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

        from apps.tenant_app_service.chat.agent_run_domain import sort_timeline_trigger_anchored
        from apps.tenant_app_service.chat.agent_run_message_repository import AgentRunMessageRepository
        from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
        from apps.tenant_app_service.chat.history_adapters import (
            agent_run_row_to_api_message,
            main_timeline_row_to_api_message,
        )
        from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository

        thread = await self.thread_repo.get_by_id(thread_id)
        include_tools = include_tool_messages if include_tool_messages is not None else True

        main_repo = MainMessageRepository(self.db)
        run_repo = AgentRunRepository(self.db)
        run_msg_repo = AgentRunMessageRepository(self.db)

        use_run_detail = include_tools or session_id is not None or before_session_id is not None

        if not use_run_detail:
            timeline = sort_timeline_trigger_anchored(await main_repo.list_for_thread(thread.id))
            api_messages = [
                main_timeline_row_to_api_message(row, thread_id=thread.id, default_agent_id=agent_id)
                for row in timeline
                if row.type in ("human", "ai")
            ]
            return ConversationHistoryResponse(
                thread_id=thread.id,
                tenant_id=thread.tenant_id,
                agent_id=thread.agent_id,
                user_id=thread.user_id,
                username=current_user.username,
                total_rounds=sum(1 for m in api_messages if m.role == "human"),
                messages=api_messages,
                message_count=len(api_messages),
                has_more=False,
            )

        runs, has_more, next_before_session_id = await run_repo.list_runs_for_history_page(
            thread_id=thread.id,
            agent_id=agent_id,
            session_limit=session_limit,
            before_session_id=before_session_id,
            session_id=session_id,
        )

        api_messages: list[Message] = []
        humans_emitted_for_trigger: set[str] = set()

        for run in runs:
            if run.trigger_message_id not in humans_emitted_for_trigger:
                humans_emitted_for_trigger.add(run.trigger_message_id)
                human = await main_repo.get_by_message_id(thread.id, run.trigger_message_id)
                if human:
                    api_messages.append(
                        main_timeline_row_to_api_message(
                            human, thread_id=thread.id, default_agent_id=agent_id
                        )
                    )

            run_rows = await run_msg_repo.list_for_run(run.id)
            if include_tools:
                for row in run_rows:
                    api_messages.append(
                        agent_run_row_to_api_message(row, thread_id=thread.id, default_agent_id=agent_id)
                    )
            promoted = await main_repo.get_promoted_ai_for_run(run.id)
            if promoted:
                if not include_tools or promoted.message_id not in {r.message_id for r in run_rows if r.message_id}:
                    api_messages.append(
                        main_timeline_row_to_api_message(promoted, thread_id=thread.id, default_agent_id=agent_id)
                    )
            elif include_tools:
                final_ai = next((r for r in reversed(run_rows) if r.type == "ai"), None)
                if final_ai:
                    api_messages.append(
                        agent_run_row_to_api_message(final_ai, thread_id=thread.id, default_agent_id=agent_id)
                    )

        return ConversationHistoryResponse(
            thread_id=thread.id,
            tenant_id=thread.tenant_id,
            agent_id=thread.agent_id,
            user_id=thread.user_id,
            username=current_user.username,
            total_rounds=sum(1 for m in api_messages if m.role == "human"),
            messages=api_messages,
            message_count=len(api_messages),
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
        from apps.tenant_app_service.chat.agent_run_message_repository import AgentRunMessageRepository
        from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository

        run_id: str | None = None
        if session_id:
            run = await AgentRunRepository(self.db).get_by_session_id(session_id)
            run_id = run.id if run else None

        run_msg_repo = AgentRunMessageRepository(self.db)
        db_msg = await run_msg_repo.get_tool_message_by_call_id(
            thread_id,
            tool_call_id,
            run_id=run_id,
        )
        if not db_msg and run_id is not None:
            db_msg = await run_msg_repo.get_tool_message_by_call_id(
                thread_id,
                tool_call_id,
                run_id=None,
            )
        if db_msg:
            from apps.tenant_app_service.agents.message_persistence_adapters import (
                agent_run_message_to_chat_message,
            )

            domain_msg = chat_message_to_domain(agent_run_message_to_chat_message(db_msg))
            return domain_message_to_api(domain_msg)

        return None

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
