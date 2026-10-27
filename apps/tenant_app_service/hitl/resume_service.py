"""Resume agent runs after HITL approval via LangGraph checkpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from apps.shared.db.models import Agent
from apps.shared.db.session import app_db_session
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.turn_service import ChatTurnService
from apps.tenant_app_service.hitl.domain import HITL_STATUS_APPROVED, HITL_STATUS_EXECUTED
from apps.tenant_app_service.hitl.repository import HitlApprovalRepository

logger = get_logger(__name__)


@dataclass(frozen=True)
class HitlResumeContext:
    """Resolved approval + run identity for a checkpoint resume stream."""

    proposal_id: str
    session_id: str
    thread_id: str
    agent_id: int
    run_id: str
    trigger_message_id: str
    invoke_index: int
    agent_name: str


class HitlResumeService:
    """Checkpoint resume after tool approval (v2 — no chat continuation)."""

    def __init__(self, tenant_id: int, db):
        self.tenant_id = tenant_id
        self.db = db

    async def prepare_resume(self, proposal_id: str, *, current_user: UserDTO) -> HitlResumeContext | None:
        """Validate approval, claim ``awaiting_hitl`` run, return resume context."""
        approval_repo = HitlApprovalRepository(self.db)
        approval = await approval_repo.get_by_proposal_id(self.tenant_id, proposal_id)
        if not approval or approval.status not in (HITL_STATUS_APPROVED, HITL_STATUS_EXECUTED):
            return None
        if approval.requested_by != current_user.id:
            return None

        run_repo = AgentRunRepository(self.db)
        run = await run_repo.get_by_session_id(approval.session_id) if approval.session_id else None
        if not run:
            logger.warning("HITL resume: no agent run for session_id=%s", approval.session_id)
            return None

        thread_runs = ThreadRunService(self.db, self.tenant_id)
        if not await thread_runs.on_resume_started(run.id):
            logger.info(
                "HITL resume skipped (run not awaiting_hitl): proposal_id=%s run_id=%s",
                proposal_id,
                run.id,
            )
            return None

        agent_row = await self.db.get(Agent, approval.agent_id)
        agent_name = agent_row.name if agent_row else f"agent-{approval.agent_id}"
        return HitlResumeContext(
            proposal_id=proposal_id,
            session_id=approval.session_id,
            thread_id=approval.thread_id,
            agent_id=approval.agent_id,
            run_id=run.id,
            trigger_message_id=run.trigger_message_id,
            invoke_index=run.invoke_index,
            agent_name=agent_name,
        )

    async def stream_resume(self, proposal_id: str, *, current_user: UserDTO) -> AsyncIterator[str]:
        """Stream SSE payloads for an approved HITL proposal (checkpoint resume)."""
        ctx = await self.prepare_resume(proposal_id, current_user=current_user)
        if ctx is None:
            return

        async for payload in self._stream_prepared(ctx, current_user=current_user):
            yield payload

    async def _stream_prepared(
        self,
        ctx: HitlResumeContext,
        *,
        current_user: UserDTO,
    ) -> AsyncIterator[str]:
        async with app_db_session() as db:
            turn = ChatTurnService(self.tenant_id, db)
            request = ChatRequest(
                tenant_id=self.tenant_id,
                agent_id=ctx.agent_id,
                thread_id=ctx.thread_id,
                message=SimpleMessage(role="human", content=""),
            )
            async for payload in turn.run_hitl_checkpoint_resume_stream(
                request=request,
                current_user=current_user,
                session_id=ctx.session_id,
                agent_id=ctx.agent_id,
                agent_name=ctx.agent_name,
                run_id=ctx.run_id,
                trigger_message_id=ctx.trigger_message_id,
                invoke_index=ctx.invoke_index,
                proposal_id=ctx.proposal_id,
            ):
                yield payload
