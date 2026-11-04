"""Persistence for in-run agent summaries."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentRunSummary
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class AgentRunSummaryRepository:
    """Tenant-scoped access to ``agent_run_summaries``."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_run(self, tenant_id: int, run_id: str) -> AgentRunSummary | None:
        result = await self.db.execute(
            select(AgentRunSummary).where(
                AgentRunSummary.tenant_id == tenant_id,
                AgentRunSummary.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        run_id: str,
        summary_text: str,
        cutoff_message_id: str | None,
        through_agent_run_message_id: int | None,
    ) -> AgentRunSummary:
        existing = await self.get_for_run(tenant_id, run_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.summary_text = summary_text
            existing.cutoff_message_id = cutoff_message_id
            existing.through_agent_run_message_id = through_agent_run_message_id
            existing.updated_at = now
            await self.db.flush()
            return existing

        row = AgentRunSummary(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            summary_text=summary_text,
            cutoff_message_id=cutoff_message_id,
            through_agent_run_message_id=through_agent_run_message_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        await self.db.flush()
        logger.debug("Upserted agent run summary for run %s", run_id)
        return row
