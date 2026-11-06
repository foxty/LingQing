"""Shared chat-turn helpers composed by ``ChatTurnService`` (messages, runs, titles)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.application.threads.thread_service import ThreadService
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse


class ChatTurnHelpersMixin:
    def _thread_runs(self) -> ThreadRunService:
        return ThreadRunService(self.db, self.tenant_id)

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

    async def run_headless(
        self,
        *,
        user_id: int,
        agent_id: int,
        message: str,
        origin_thread_id: str | None = None,
        task_name: str | None = None,
    ) -> ChatResponse:
        """Run a chat turn on behalf of a user without an HTTP request."""
        from apps.tenant_app_service.chat.application import run_headless_chat_turn

        return await run_headless_chat_turn(
            self.tenant_id,
            self.db,
            user_id=user_id,
            agent_id=agent_id,
            message=message,
            origin_thread_id=origin_thread_id,
            task_name=task_name,
        )

    async def chat(self, request: ChatRequest, current_user: UserDTO, access_token: str | None = None) -> ChatResponse:
        """Handle non-streaming chat (prepare + complete via short DB sessions)."""
        from apps.tenant_app_service.chat.application.turn_flow import run_non_stream_chat_turn

        return await run_non_stream_chat_turn(
            self.tenant_id,
            request,
            current_user,
            access_token=access_token,
        )

    async def create_thread_title_if_1st_message(self, content: str, thread_id: str, session_id: str) -> str:
        thread = await ThreadService(self.tenant_id, self.db).get_thread(thread_id)
        if thread is None:
            return None
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

    def _build_initial_agent_messages(self, lc_messages: list, request: ChatRequest) -> list:
        """Build agent initial state messages.

        Normal sends persist the human message before invocation, so only ephemeral
        system context is passed in state.
        """
        del request
        return [message for message in lc_messages if isinstance(message, SystemMessage)]
