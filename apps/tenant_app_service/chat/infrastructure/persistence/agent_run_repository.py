"""Infrastructure — agent_runs persistence (implements ``AgentRunRepositoryPort``)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentRun as AgentRunRow
from apps.tenant_app_service.chat.domain.agent_run.state import AgentRunState
from apps.tenant_app_service.chat.domain.agent_run.status import (
    ACTIVE_AGENT_RUN_STATUSES,
    CANCELLABLE_AGENT_RUN_STATUSES,
    AgentRunStatus,
)


def _to_state(row: AgentRunRow) -> AgentRunState:
    return AgentRunState(
        id=row.id,
        tenant_id=row.tenant_id,
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        trigger_message_id=row.trigger_message_id,
        invoke_index=row.invoke_index,
        status=row.status,
        session_id=row.session_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


class AgentRunRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        agent_id: int,
        trigger_message_id: str,
        invoke_index: int,
        session_id: str,
        status: str = AgentRunStatus.QUEUED,
    ) -> AgentRunState:
        run_id = str(uuid4())
        now = datetime.now(UTC)
        row = AgentRunRow(
            id=run_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            agent_id=agent_id,
            trigger_message_id=trigger_message_id,
            invoke_index=invoke_index,
            status=status,
            session_id=session_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        await self.db.flush()
        return _to_state(row)

    async def get_by_session_id(self, session_id: str) -> AgentRunState | None:
        result = await self.db.execute(select(AgentRunRow).where(AgentRunRow.session_id == session_id).limit(1))
        row = result.scalar_one_or_none()
        return _to_state(row) if row else None

    async def get_latest_for_thread_agent(self, thread_id: str, agent_id: int) -> AgentRunState | None:
        result = await self.db.execute(
            select(AgentRunRow)
            .where(AgentRunRow.thread_id == thread_id, AgentRunRow.agent_id == agent_id)
            .order_by(AgentRunRow.created_at.desc(), AgentRunRow.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_state(row) if row else None

    async def list_active_for_thread_agent(self, thread_id: str, agent_id: int) -> list[AgentRunState]:
        result = await self.db.execute(
            select(AgentRunRow)
            .where(
                AgentRunRow.thread_id == thread_id,
                AgentRunRow.agent_id == agent_id,
                AgentRunRow.status.in_(tuple(ACTIVE_AGENT_RUN_STATUSES)),
            )
            .order_by(AgentRunRow.created_at.desc())
        )
        return [_to_state(row) for row in result.scalars().all()]

    async def list_runs_for_history_page(
        self,
        *,
        thread_id: str,
        agent_id: int,
        session_limit: int,
        before_session_id: str | None,
        session_id: str | None,
    ) -> tuple[list[AgentRunState], bool, str | None]:
        query = (
            select(AgentRunRow)
            .where(AgentRunRow.thread_id == thread_id, AgentRunRow.agent_id == agent_id)
            .order_by(AgentRunRow.created_at.desc(), AgentRunRow.id.desc())
        )
        if session_id:
            query = query.where(AgentRunRow.session_id == session_id)
        result = await self.db.execute(query)
        runs_desc = [_to_state(row) for row in result.scalars().all()]

        if before_session_id:
            idx = next((i for i, r in enumerate(runs_desc) if r.session_id == before_session_id), None)
            if idx is not None:
                runs_desc = runs_desc[idx + 1 :]

        has_more = len(runs_desc) > session_limit
        page_desc = runs_desc[:session_limit]
        page_asc = list(reversed(page_desc))
        next_before = page_desc[-1].session_id if has_more and page_desc else None
        return page_asc, has_more, next_before

    async def get_run(self, tenant_id: int, run_id: str) -> AgentRunState | None:
        result = await self.db.execute(
            select(AgentRunRow).where(AgentRunRow.id == run_id, AgentRunRow.tenant_id == tenant_id)
        )
        row = result.scalar_one_or_none()
        return _to_state(row) if row else None

    async def list_for_trigger(self, thread_id: str, trigger_message_id: str) -> list[AgentRunState]:
        result = await self.db.execute(
            select(AgentRunRow)
            .where(
                AgentRunRow.thread_id == thread_id,
                AgentRunRow.trigger_message_id == trigger_message_id,
            )
            .order_by(AgentRunRow.invoke_index.asc())
        )
        return [_to_state(row) for row in result.scalars().all()]

    async def list_for_thread(self, thread_id: str) -> list[AgentRunState]:
        result = await self.db.execute(
            select(AgentRunRow)
            .where(AgentRunRow.thread_id == thread_id)
            .order_by(AgentRunRow.created_at.asc(), AgentRunRow.id.asc())
        )
        return [_to_state(row) for row in result.scalars().all()]

    async def list_for_triggers(
        self,
        thread_id: str,
        trigger_message_ids: list[str],
    ) -> dict[str, list[AgentRunState]]:
        if not trigger_message_ids:
            return {}
        result = await self.db.execute(
            select(AgentRunRow)
            .where(
                AgentRunRow.thread_id == thread_id,
                AgentRunRow.trigger_message_id.in_(trigger_message_ids),
            )
            .order_by(AgentRunRow.invoke_index.asc())
        )
        grouped: dict[str, list[AgentRunState]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.trigger_message_id, []).append(_to_state(row))
        return grouped

    async def set_status(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        completed_at: datetime | None = None,
    ) -> None:
        values: dict = {"status": status.value, "updated_at": datetime.now(UTC)}
        if completed_at is not None:
            values["completed_at"] = completed_at
        await self.db.execute(update(AgentRunRow).where(AgentRunRow.id == run_id).values(**values))

    async def cancel_active_run(
        self,
        tenant_id: int,
        run_id: str,
        *,
        completed_at: datetime,
    ) -> AgentRunState | None:
        """Move run to ``cancelled`` when queued, running, or awaiting HITL; returns None if no row matched."""
        now = datetime.now(UTC)
        cancellable = tuple(s.value for s in CANCELLABLE_AGENT_RUN_STATUSES)
        result = await self.db.execute(
            update(AgentRunRow)
            .where(
                AgentRunRow.id == run_id,
                AgentRunRow.tenant_id == tenant_id,
                AgentRunRow.status.in_(cancellable),
            )
            .values(
                status=AgentRunStatus.CANCELLED.value,
                completed_at=completed_at,
                updated_at=now,
            )
            .returning(AgentRunRow)
        )
        row = result.scalar_one_or_none()
        return _to_state(row) if row else None

    async def transition_status(
        self,
        run_id: str,
        *,
        expected: AgentRunStatus,
        new: AgentRunStatus,
    ) -> bool:
        result = await self.db.execute(
            update(AgentRunRow)
            .where(AgentRunRow.id == run_id, AgentRunRow.status == expected.value)
            .values(status=new.value, updated_at=datetime.now(UTC))
            .returning(AgentRunRow.id)
        )
        return result.first() is not None

    async def count_active_for_thread(self, thread_id: str, agent_id: int | None = None) -> int:
        query = select(AgentRunRow).where(
            AgentRunRow.thread_id == thread_id,
            AgentRunRow.status.in_(tuple(ACTIVE_AGENT_RUN_STATUSES)),
        )
        if agent_id is not None:
            query = query.where(AgentRunRow.agent_id == agent_id)
        result = await self.db.execute(query)
        return len(result.scalars().all())
