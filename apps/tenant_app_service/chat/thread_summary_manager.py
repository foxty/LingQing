"""Thread summary manager and trigger logic."""

from dataclasses import dataclass

from langchain_core.messages import SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatThread, SessionSummary, ThreadSummary
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.token_counter import count_tokens
from apps.tenant_app_service.chat.adapters import session_summary_to_domain, thread_summary_domain_to_db
from apps.tenant_app_service.chat.domain import SessionSummaryDomain, ThreadSummaryDomain
from apps.tenant_app_service.chat.session_summary_repository import SessionSummaryRepository
from apps.tenant_app_service.chat.thread_summary_repository import ThreadSummaryRepository

logger = get_logger(__name__)


@dataclass
class TriggerResult:
    """Thread summary trigger check result."""

    should_trigger: bool
    reason: str
    session_count: int
    estimated_tokens: int

    def __str__(self) -> str:
        return (
            f"TriggerResult(should_trigger={self.should_trigger}, reason='{self.reason}', "
            f"session_count={self.session_count}, estimated_tokens={self.estimated_tokens})"
        )


class ThreadSummaryTrigger:
    """Thread summary trigger using hybrid strategy."""

    STANDARD_SESSION_WINDOW = 5
    EARLY_TRIGGER_MIN_SESSIONS = 3
    EARLY_TRIGGER_TOKEN_THRESHOLD = 18000
    LATE_TRIGGER_MAX_SESSIONS = 7
    LATE_TRIGGER_MIN_TOKENS = 6000

    async def check(
        self,
        thread_id: str,
        unsummarized_sessions: list[SessionSummary],
    ) -> TriggerResult:
        """Check if thread summary should be created.

        Args:
            thread_id: Thread ID
            unsummarized_sessions: List of unsummarized session summaries

        Returns:
            TriggerResult with decision
        """
        session_count = len(unsummarized_sessions)
        session_messages = [SystemMessage(content=f"{s.summary_text}") for s in unsummarized_sessions]
        estimated_tokens = count_tokens(session_messages)

        # Rule 1: Standard window (only when input is large enough to benefit from compression)
        if session_count == self.STANDARD_SESSION_WINDOW:
            if estimated_tokens < self.LATE_TRIGGER_MIN_TOKENS:
                return TriggerResult(
                    should_trigger=False,
                    reason="delaying_light_sessions_at_window",
                    session_count=session_count,
                    estimated_tokens=estimated_tokens,
                )
            return TriggerResult(
                should_trigger=True,
                reason="standard_window",
                session_count=session_count,
                estimated_tokens=estimated_tokens,
            )

        # Rule 2: Early trigger (heavy sessions)
        if session_count >= self.EARLY_TRIGGER_MIN_SESSIONS and estimated_tokens >= self.EARLY_TRIGGER_TOKEN_THRESHOLD:
            logger.warning(
                f"Early trigger for thread {thread_id}: {session_count} sessions with {estimated_tokens} tokens"
            )
            return TriggerResult(
                should_trigger=True,
                reason="early_trigger_heavy_sessions",
                session_count=session_count,
                estimated_tokens=estimated_tokens,
            )

        # Rule 3: Late trigger handling (light sessions)
        if session_count > self.STANDARD_SESSION_WINDOW:
            # Max sessions reached
            if session_count >= self.LATE_TRIGGER_MAX_SESSIONS:
                return TriggerResult(
                    should_trigger=True,
                    reason="late_trigger_max_sessions",
                    session_count=session_count,
                    estimated_tokens=estimated_tokens,
                )

            # Tokens still too low, continue delaying
            if estimated_tokens < self.LATE_TRIGGER_MIN_TOKENS:
                return TriggerResult(
                    should_trigger=False,
                    reason="delaying_light_sessions",
                    session_count=session_count,
                    estimated_tokens=estimated_tokens,
                )

            # Sufficient tokens, trigger
            return TriggerResult(
                should_trigger=True,
                reason="late_trigger_sufficient_tokens",
                session_count=session_count,
                estimated_tokens=estimated_tokens,
            )

        # Default: wait
        return TriggerResult(
            should_trigger=False,
            reason="waiting",
            session_count=session_count,
            estimated_tokens=estimated_tokens,
        )


class ThreadSummaryManager:
    """Manages thread-level summarization."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        """Initialize thread summary manager.

        Args:
            db: Database session
            tenant_id: Tenant ID
        """
        self.db = db
        self.tenant_id = tenant_id
        self.repo = ThreadSummaryRepository(db)
        self.session_repo = SessionSummaryRepository(db)
        self.trigger = ThreadSummaryTrigger()
        self._mini_agent_service = None

    async def check_and_create_if_needed(self, thread_id: str) -> ThreadSummary | None:
        """Check if thread summary is needed and create it.

        Args:
            thread_id: Thread ID

        Returns:
            Created ThreadSummary or None if not needed
        """
        unsummarized = await self.session_repo.get_unsummarized_sessions(thread_id)
        result = await self.trigger.check(thread_id, unsummarized)
        logger.info(f"Thread summary check for {thread_id}: {result} ")
        if result.should_trigger:
            return await self.create_thread_summary(thread_id, unsummarized)
        else:
            return None

    async def create_thread_summary(
        self,
        thread_id: str,
        session_summaries: list[SessionSummary],
    ) -> ThreadSummary | None:
        """Create a thread summary from session summaries.

        Orchestrates summary generation, delegates business logic to domain, handles persistence.

        Args:
            thread_id: Thread ID
            session_summaries: List of SessionSummary DB models

        Returns:
            Created ThreadSummary DB model or None if creation failed
        """
        if not session_summaries:
            logger.warning(f"No session summaries provided for thread {thread_id}")
            return None

        try:
            # Get next version
            current_version = await self.repo.get_latest_version(thread_id)
            new_version = current_version + 1

            # Convert DB models to domain (at the boundary)
            session_domains = [session_summary_to_domain(ss) for ss in session_summaries]

            # Try to generate LLM summary (orchestrated by manager)
            llm_summary = await self._try_generate_llm_summary(thread_id, session_domains)

            # Delegate to domain: create with LLM or fallback summary
            if llm_summary:
                # Use LLM-generated summary
                thread_summary_domain = ThreadSummaryDomain.create_from_sessions(
                    thread_id=thread_id,
                    tenant_id=self.tenant_id,
                    version=new_version,
                    sessions=session_domains,
                    summary_content=llm_summary,
                )
            else:
                # Use domain's fallback summary logic
                logger.warning(f"Using fallback summary for thread {thread_id}")
                thread_summary_domain = ThreadSummaryDomain.create_with_fallback_summary(
                    thread_id=thread_id,
                    tenant_id=self.tenant_id,
                    version=new_version,
                    sessions=session_domains,
                )

            # Convert domain to DB model (at the boundary)
            thread_summary_db = thread_summary_domain_to_db(thread_summary_domain)

            # Persist to database
            await self.repo.create(thread_summary_db)

            # Update ChatThread summary_count
            thread = await self.db.get(ChatThread, thread_id)
            if thread:
                thread.summary_count += 1

            # Mark sessions as summarized
            session_ids = [s.session_id for s in session_summaries]
            await self.session_repo.mark_sessions_as_summarized(session_ids, new_version)

            await self.db.commit()

            logger.info(
                f"Created thread summary v{new_version} for thread {thread_id}: "
                f"{len(session_summaries)} sessions, "
                f"tokens: {thread_summary_domain.token_count_before} → "
                f"{thread_summary_domain.token_count_after} "
                f"({thread_summary_domain.format_token_metrics()})"
            )

            return thread_summary_db

        except Exception as e:
            logger.error(f"Failed to create thread summary for {thread_id}: {e}", exc_info=True)
            await self.db.rollback()
            return None

    async def _try_generate_llm_summary(
        self,
        thread_id: str,
        sessions: list[SessionSummaryDomain],
    ) -> str | None:
        """Try to generate summary using LLM service.

        Manager orchestrates service calls. Returns None on failure,
        letting caller decide whether to use domain fallback.

        Args:
            thread_id: Thread ID
            sessions: List of SessionSummaryDomain objects

        Returns:
            LLM-generated summary content or None if failed
        """
        try:
            # Initialize MiniAgentService lazily if needed
            if self._mini_agent_service is None:
                from apps.tenant_app_service.agents.mini_agent import MiniAgentService

                self._mini_agent_service = MiniAgentService.create(self.db, self.tenant_id)
            session_dicts = [
                {
                    "session_id": s.session_id,
                    "summary": s.summary,
                }
                for s in sessions
            ]

            # Try LLM summarization
            result = await self._mini_agent_service.summarize_thread(
                thread_id=thread_id,
                session_summaries=session_dicts,
            )

            if result:
                return result.strip()
            else:
                logger.warning(f"MiniAgent returned no summary for thread: {thread_id}")
                return None

        except Exception as e:
            logger.warning(f"Failed to generate summary with LLM: {e}", exc_info=True)
            return None
