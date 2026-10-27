"""Write-side orchestration for main timeline + agent runs (single DB session).

**Layer:** Session-scoped service — persist human rows, create/update ``agent_runs``,
assemble timeline reads. No LangGraph / SSE.
**Callers:** ``ChatTurnService`` prepare and promotion paths.
**Contrast:** ``ThreadService`` = thread CRUD + history reads; ``ChatTurnService`` = agent invoke.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatThread
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.agent_run_domain import (
    AgentRunDomain,
    AgentRunStatus,
    ThreadMainMessageDomain,
    find_promotable_final_ai_row,
    sort_timeline_trigger_anchored,
)
from apps.tenant_app_service.chat.agent_run_message_repository import AgentRunMessageRepository
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository

logger = get_logger(__name__)


class ThreadRunService:
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.main_repo = MainMessageRepository(db)
        self.run_repo = AgentRunRepository(db)
        self.run_message_repo = AgentRunMessageRepository(db)

    async def send_human_and_create_runs(
        self,
        *,
        thread_id: str,
        content: str,
        agent_ids: list[int],
        message_metadata: dict | None = None,
    ) -> tuple[str, list]:
        """Persist one human on main and create agent runs (0..N)."""
        message_id = str(uuid4())
        await self.main_repo.insert_human(
            message_id=message_id,
            thread_id=thread_id,
            content=content,
            message_metadata=message_metadata,
        )
        thread = await self.db.get(ChatThread, thread_id)
        if thread:
            thread.message_count = (thread.message_count or 0) + 1

        runs = []
        for invoke_index, agent_id in enumerate(agent_ids):
            session_id = str(uuid4())
            run = await self.run_repo.create_run(
                tenant_id=self.tenant_id,
                thread_id=thread_id,
                agent_id=agent_id,
                trigger_message_id=message_id,
                invoke_index=invoke_index,
                session_id=session_id,
            )
            runs.append(run)

        return message_id, runs

    async def mark_run_running(self, run_id: str) -> None:
        await self.run_repo.set_status(run_id, status=AgentRunStatus.RUNNING)

    async def mark_run_awaiting_hitl(self, run_id: str) -> None:
        await self.run_repo.set_status(run_id, status=AgentRunStatus.AWAITING_HITL)

    async def mark_run_completed(self, run_id: str) -> None:
        await self.run_repo.set_status(
            run_id,
            status=AgentRunStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )

    async def mark_run_failed(self, run_id: str) -> None:
        await self.run_repo.set_status(
            run_id,
            status=AgentRunStatus.FAILED,
            completed_at=datetime.now(UTC),
        )

    async def promote_final_ai(
        self,
        *,
        run_id: str,
        thread_id: str,
        agent_id: int,
        trigger_message_id: str,
        invoke_index: int,
        session_id: str,
        final_message: AIMessage,
    ) -> ThreadMainMessageDomain | None:
        existing = await self.main_repo.get_promoted_ai_for_run(run_id)
        if existing:
            return existing

        from apps.tenant_app_service.agents.message_content import normalize_message_content

        message_id = final_message.id or str(uuid4())
        content = normalize_message_content(final_message.content)
        kwargs = final_message.additional_kwargs or {}
        row = await self.main_repo.insert_promoted_ai(
            message_id=str(message_id),
            thread_id=thread_id,
            content=content,
            agent_id=agent_id,
            trigger_message_id=trigger_message_id,
            agent_run_id=run_id,
            invoke_index=invoke_index,
            session_id=session_id,
            additional_kwargs=kwargs,
        )
        thread = await self.db.get(ChatThread, thread_id)
        if thread:
            thread.message_count = (thread.message_count or 0) + 1
        return row

    async def finalize_run_for_main(self, run_id: str) -> None:
        """Promote terminal run AI to main timeline and close the run when appropriate.

        Called after turn execution (or terminal HITL resolution), not from LangGraph nodes.
        Skips promotion while the run is paused for HITL or already failed/cancelled.
        """
        run = await self.run_repo.get_run(self.tenant_id, run_id)
        if not run:
            return

        if run.status in (
            AgentRunStatus.AWAITING_HITL,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        ):
            return

        if not await self.main_repo.get_promoted_ai_for_run(run_id):
            run_rows = await self.run_message_repo.list_for_run(run_id)
            final_row = find_promotable_final_ai_row(run_rows)
            if final_row is not None:
                from apps.tenant_app_service.agents.message_persistence_adapters import (
                    agent_run_message_to_langchain,
                )

                lc_message = agent_run_message_to_langchain(final_row)
                if isinstance(lc_message, AIMessage):
                    await self.promote_final_ai(
                        run_id=run_id,
                        thread_id=run.thread_id,
                        agent_id=run.agent_id,
                        trigger_message_id=run.trigger_message_id,
                        invoke_index=run.invoke_index,
                        session_id=run.session_id,
                        final_message=lc_message,
                    )

        if run.status == AgentRunStatus.RUNNING:
            await self.mark_run_completed(run_id)

    async def get_timeline(self, thread_id: str) -> list[ThreadMainMessageDomain]:
        rows = await self.main_repo.list_for_thread(thread_id)
        return sort_timeline_trigger_anchored(rows)

    async def list_runs_for_trigger(self, thread_id: str, trigger_message_id: str) -> list[AgentRunDomain]:
        return await self.run_repo.list_for_trigger(thread_id, trigger_message_id)

    async def load_trigger_human_langchain(
        self,
        thread_id: str,
        trigger_message_id: str,
    ) -> HumanMessage | None:
        domain = await self.main_repo.get_by_message_id(thread_id, trigger_message_id)
        if not domain:
            return None
        return HumanMessage(id=domain.message_id, content=domain.content)
