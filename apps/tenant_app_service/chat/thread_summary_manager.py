"""Cumulative thread summary: merge the previous status with pairs that aged out of the main-line tail."""

from langchain_core.messages import SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatThread, ThreadSummary
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.memory.memory_budget import (
    THREAD_SUMMARY_MAX_TOKENS,
    THREAD_SUMMARY_MIN_AGED_PAIRS,
    THREAD_SUMMARY_TURN_FIELD_CHARS,
    thread_summary_context_pressure_tokens,
)
from apps.tenant_app_service.agents.token_counter import count_tokens
from apps.tenant_app_service.chat.adapters import thread_summary_domain_to_db
from apps.tenant_app_service.chat.domain import (
    ThreadMainMessageDomain,
    ThreadSummaryDomain,
    aged_out_uncovered_turns,
    context_pair_turns,
    iter_thread_pair_turns,
    sort_timeline_trigger_anchored,
)
from apps.tenant_app_service.chat.infrastructure.persistence import (
    AgentRunMessageRepository,
    AgentRunSummaryRepository,
    MainMessageRepository,
    ThreadSummaryRepository,
)
from apps.tenant_app_service.chat.service_base import DEFAULT_MAIN_TIMELINE_TURN_LIMIT

logger = get_logger(__name__)


def _clip(text: str) -> str:
    """Cap turn fields sent to the thread summarizer (not the stored summary text)."""
    if len(text) <= THREAD_SUMMARY_TURN_FIELD_CHARS:
        return text
    return text[:THREAD_SUMMARY_TURN_FIELD_CHARS] + "..."


def _estimate_verbatim_tail_tokens(
    rows: list[ThreadMainMessageDomain],
    *,
    through_trigger_message_id: str | None,
) -> int:
    """Rough token count for main-line pairs kept verbatim beside the thread summary."""
    pair_turns = list(iter_thread_pair_turns(rows))
    kept = context_pair_turns(
        pair_turns,
        through_trigger_message_id=through_trigger_message_id,
        reserve_tail=DEFAULT_MAIN_TIMELINE_TURN_LIMIT,
    )
    chunks = [
        f"{row.type}: {row.content}"
        for turn in kept
        for row in turn
        if row.content
    ]
    if not chunks:
        return 0
    return count_tokens([SystemMessage(content=chunk) for chunk in chunks])


def should_write_thread_summary_delta(
    *,
    delta: list[list[ThreadMainMessageDomain]],
    previous_summary: str | None,
    main_rows: list[ThreadMainMessageDomain],
    through_trigger_message_id: str | None,
) -> tuple[bool, str]:
    """Whether pending aged-out pairs should be merged now (vs left for the next run)."""
    if not delta:
        return False, "no_delta"

    if len(delta) >= THREAD_SUMMARY_MIN_AGED_PAIRS:
        return True, "batch_threshold"

    if previous_summary:
        summary_tokens = count_tokens([SystemMessage(content=previous_summary)])
        if summary_tokens > THREAD_SUMMARY_MAX_TOKENS:
            return True, "summary_over_max"

        tail_tokens = _estimate_verbatim_tail_tokens(
            main_rows,
            through_trigger_message_id=through_trigger_message_id,
        )
        pressure = thread_summary_context_pressure_tokens()
        if summary_tokens + tail_tokens >= pressure:
            return True, "context_pressure"

    return False, "defer_batch"


class ThreadSummaryManager:
    """Writes the next cumulative thread summary after a run completes."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.repo = ThreadSummaryRepository(db)
        self.main_repo = MainMessageRepository(db)
        self.run_summary_repo = AgentRunSummaryRepository(db)
        self.run_message_repo = AgentRunMessageRepository(db)
        self._mini_agent_service = None

    async def check_and_create_if_needed(self, thread_id: str) -> ThreadSummary | None:
        """Create the next cumulative version when aged-out pairs should be folded.

        The check runs after every terminal run; the LLM runs only when batch or
        context-pressure rules say so. A failed summarizer leaves the previous version.
        """
        rows = sort_timeline_trigger_anchored(await self.main_repo.list_for_thread(thread_id))
        latest_rows = await self.repo.get_recent_summaries(thread_id, limit=1)
        previous = latest_rows[0] if latest_rows else None
        watermark = previous.through_trigger_message_id if previous is not None else None
        delta = aged_out_uncovered_turns(
            rows,
            reserve_tail=DEFAULT_MAIN_TIMELINE_TURN_LIMIT,
            through_trigger_message_id=watermark,
        )
        if not delta:
            logger.info("Thread summary skipped for %s: no aged-out pairs", thread_id)
            return None

        previous_text = previous.summary_content if previous is not None else None
        should_write, reason = should_write_thread_summary_delta(
            delta=delta,
            previous_summary=previous_text,
            main_rows=rows,
            through_trigger_message_id=watermark,
        )
        if not should_write:
            logger.info(
                "Thread summary deferred for %s: %s aged-out pair(s) (%s)",
                thread_id,
                len(delta),
                reason,
            )
            return None

        try:
            return await self._write_cumulative(thread_id, previous, delta, write_reason=reason)
        except Exception as exc:
            logger.error("Failed to create thread summary for %s: %s", thread_id, exc, exc_info=True)
            await self.db.rollback()
            return None

    async def _write_cumulative(
        self,
        thread_id: str,
        previous: ThreadSummary | None,
        delta: list[list[ThreadMainMessageDomain]],
        *,
        write_reason: str,
    ) -> ThreadSummary | None:
        previous_text = previous.summary_content if previous is not None else None
        recompress = False
        if previous_text:
            recompress = count_tokens([SystemMessage(content=previous_text)]) > THREAD_SUMMARY_MAX_TOKENS

        turn_blocks = []
        for turn in delta:
            turn_blocks.append(await self._format_turn_for_summary(turn))

        summary_content = await self._summarize(
            thread_id,
            previous_summary=previous_text,
            turn_blocks=turn_blocks,
            recompress=recompress,
        )
        if not summary_content:
            logger.warning("Thread summarizer returned no text for %s; keeping previous version", thread_id)
            return None

        current_version = await self.repo.get_latest_version(thread_id)
        new_version = current_version + 1
        through_trigger_message_id = delta[-1][0].message_id
        session_ids = [row.session_id for turn in delta for row in turn if row.session_id]
        times = [row.timestamp for turn in delta for row in turn if row.timestamp]
        prompt_tokens = count_tokens([SystemMessage(content=block) for block in turn_blocks])
        if previous_text:
            prompt_tokens += count_tokens([SystemMessage(content=previous_text)])
        domain = ThreadSummaryDomain.create_cumulative(
            thread_id=thread_id,
            tenant_id=self.tenant_id,
            version=new_version,
            through_trigger_message_id=through_trigger_message_id,
            summary_content=summary_content,
            session_range={
                "from_session_id": session_ids[0] if session_ids else None,
                "to_session_id": session_ids[-1] if session_ids else None,
                "session_count": len(delta),
                "from_trigger_message_id": delta[0][0].message_id,
                "to_trigger_message_id": through_trigger_message_id,
            },
            message_range={
                "from_time": min(times).isoformat() if times else None,
                "to_time": max(times).isoformat() if times else None,
                "count": sum(len(turn) for turn in delta),
            },
            session_count=len(delta),
            token_count_before=prompt_tokens,
            token_count_after=count_tokens([SystemMessage(content=summary_content)]),
        )
        row = thread_summary_domain_to_db(domain)
        await self.repo.create(row)
        thread = await self.db.get(ChatThread, thread_id)
        if thread:
            thread.summary_count += 1
        await self.db.commit()
        logger.info(
            "Created cumulative thread summary v%s for %s (%s): %s aged-out pair(s) through %s",
            new_version,
            thread_id,
            write_reason,
            len(delta),
            through_trigger_message_id,
        )
        return row

    async def _format_turn_for_summary(self, turn: list[ThreadMainMessageDomain]) -> str:
        """One user trigger with every promoted reply and run-level detail for that turn."""
        human = next(row for row in turn if row.type == "human")
        lines = [f"User: {_clip(human.content)}"]
        ai_rows = [row for row in turn if row.type == "ai"]
        for index, ai in enumerate(ai_rows, start=1):
            header = "Assistant"
            if len(ai_rows) > 1:
                header = f"Assistant invoke {index}"
            if ai.agent_id is not None:
                header = f"{header} (agent {ai.agent_id})"
            lines.append(f"{header}: {_clip(ai.content)}")
            if not ai.agent_run_id:
                continue
            run_detail = await self._run_detail_for_summary(ai.agent_run_id, ai.agent_id)
            if run_detail:
                lines.append(f"Run detail: {_clip(run_detail)}")
        return "\n".join(lines)

    async def _run_detail_for_summary(self, run_id: str, agent_id: int | None) -> str | None:
        """Prefer persisted in-run summary; otherwise a clipped run transcript."""
        row = await self.run_summary_repo.get_for_run(self.tenant_id, run_id)
        if row is not None and row.summary_text:
            return row.summary_text

        messages = await self.run_message_repo.list_for_run(run_id)
        if not messages:
            return None
        lines: list[str] = []
        for message in messages:
            if agent_id is not None and message.agent_id != agent_id:
                continue
            content = message.content or ""
            if not content.strip():
                continue
            lines.append(f"{message.type}: {_clip(content)}")
        return "\n".join(lines) if lines else None

    async def _summarize(
        self,
        thread_id: str,
        *,
        previous_summary: str | None,
        turn_blocks: list[str],
        recompress: bool,
    ) -> str | None:
        if self._mini_agent_service is None:
            from apps.tenant_app_service.agents.mini_agent import MiniAgentService

            self._mini_agent_service = MiniAgentService.create(self.db, self.tenant_id)
        return await self._mini_agent_service.summarize_thread_status(
            thread_id=thread_id,
            previous_summary=previous_summary,
            aged_out_turns=turn_blocks,
            recompress=recompress,
        )
