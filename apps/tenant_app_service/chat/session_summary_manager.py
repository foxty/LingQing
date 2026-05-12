"""Session summary manager for creating session-level summaries."""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import SessionSummary
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.domain import MessageDomain, SessionSummaryDomain
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.session_summary_repository import SessionSummaryRepository

logger = get_logger(__name__)


class SessionSummaryManager:
    """Manages session-level summarization."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        """Initialize session summary manager.

        Args:
            db: Database session
            tenant_id: Tenant ID for mini-agent service
        """
        self.db = db
        self.tenant_id = tenant_id
        self.repo = SessionSummaryRepository(db)
        self.message_repo = MessageRepository(db)
        self._mini_agent_service = None

    async def create_session_summary(
        self,
        session_id: str,
        thread_id: str,
    ) -> SessionSummary | None:
        """Create a session summary by loading messages from DB.

        Args:
            session_id: Session ID
            thread_id: Thread ID

        Returns:
            Created SessionSummary or None if creation failed
        """
        try:
            # 1. Load messages from DB
            db_messages = await self.message_repo.get_messages_by_session(session_id)

            if not db_messages:
                logger.warning(f"No messages found for session {session_id}, skipping summary")
                return None

            # 2. Convert DB models to domain models (adapter layer responsibility)
            from apps.tenant_app_service.chat.adapters import chat_messages_to_domain_list

            messages = chat_messages_to_domain_list(db_messages)

            # 3. Create domain model with converted messages
            session = SessionSummaryDomain.from_messages(session_id, thread_id, messages)

            # 4. Extract session information via domain properties
            user_intent = session.user_intent
            tools_used = session.tools_used
            key_results = session.key_results
            message_range = session.message_time_range

            # 4. Optionally generate detailed summary with LLM
            summary_text = None
            # Only use LLM for session with sufficient messages and tool usage
            if session.ready_for_llm_summary():
                logger.info(f"Generating detailed summary for session {session_id} using LLM")
                summary_text = await self._generate_summary_by_mini_agent(
                    thread_id=thread_id,
                    session_id=session_id,
                    messages=messages,
                )
                if summary_text is None:
                    logger.warning(
                        f"LLM summary generation failed for session {session_id}, fallback to domain generated text"
                    )
                    summary_text = session.gen_summary_text()
            else:
                logger.info(f"Skipping LLM summary for session {session_id}, using generated text")
                summary_text = session.gen_summary_text()

            # 5. Create and save session summary
            session_summary = SessionSummary(
                session_id=session_id,
                thread_id=thread_id,
                tenant_id=self.tenant_id,
                user_intent=user_intent,
                tools_used=tools_used,
                key_results=key_results,
                summary_text=summary_text,
                message_range=message_range,
            )

            await self.repo.create(session_summary)

            # Mark session messages as summarized.
            message_ids = [m.message_id for m in db_messages if m.message_id]
            await self.message_repo.mark_messages_as_summarized(message_ids, session_summary.id)

            logger.info(
                f"Created session summary for session {session_id}: "
                f"intent='{user_intent[:50]}...', tools={len(tools_used)}"
            )

            return session_summary

        except Exception as e:
            logger.error(f"Failed to create session summary for {session_id}: {e}", exc_info=True)
            return None

    async def _generate_summary_by_mini_agent(
        self,
        thread_id: str,
        session_id: str,
        messages: list[MessageDomain],
    ) -> str | None:
        """Generate detailed summary text using MiniAgent.

        Uses the specialized summarize_session method for semantic clarity.

        Args:
            user_intent: User's intent
            tools_used: List of tools used
            key_results: Key results
            session_id: Session ID for context
            thread_id: Thread ID for context

        Returns:
            Summary text or None if generation failed
        """
        try:
            from apps.tenant_app_service.agents.mini_agent import MiniAgentService

            if self._mini_agent_service is None:
                self._mini_agent_service = MiniAgentService.create(self.db, self.tenant_id)

            result = await self._mini_agent_service.summarize_session(
                thread_id=thread_id, session_id=session_id, messages=messages
            )
            return result if result else None
        except Exception as e:
            logger.warning(f"Failed to generate summary text with LLM: {e}", exc_info=True)
            return None
