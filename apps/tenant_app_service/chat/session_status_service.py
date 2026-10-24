"""Read-side session status for durable chat polling (single DB session).

**Layer:** Session-scoped application service — composes repos + HITL; returns DTOs.
**Callers:** ``ThreadService``, ``turn_admission``.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.chat.agent_run_domain import (
    ACTIVE_AGENT_RUN_STATUSES,
    AgentRunDomain,
    AgentRunStatus,
)
from apps.tenant_app_service.chat.agent_run_message_repository import AgentRunMessageRepository
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository
from apps.tenant_app_service.chat.schemas import (
    ApprovedHitlInfo,
    PendingHitlInfo,
    SessionStatusResponse,
)
from apps.tenant_app_service.chat.session_domain import (
    SESSION_STATUS_AWAITING_HITL,
    SESSION_STATUS_COMPLETED,
    SESSION_STATUS_HITL_APPROVED_PENDING_CONTINUE,
    SESSION_STATUS_RUNNING,
    is_stale_running_session,
)
from apps.tenant_app_service.hitl.repository import HitlApprovalRepository


async def _has_ai_response(
    *,
    main_repo: MainMessageRepository,
    run_msg_repo: AgentRunMessageRepository,
    thread_id: str,
    agent_id: int,
    session_id: str | None,
) -> bool:
    if not session_id:
        return False
    if await main_repo.has_promoted_ai_for_session(thread_id, session_id):
        return True
    return await run_msg_repo.has_ai_for_session(thread_id, agent_id, session_id)


def _is_orphan_active_run(
    run: AgentRunDomain,
    *,
    has_ai: bool,
    has_promoted: bool,
) -> bool:
    """Drop active runs that never closed (stale) so polling can finish."""
    stale = is_stale_running_session(run.created_at)
    if not has_ai and stale:
        return True
    if has_ai and not has_promoted and stale:
        return True
    return False


def _session_status_for_run(run: AgentRunDomain) -> str:
    """Map agent_runs.status to API session status."""
    if run.status == AgentRunStatus.AWAITING_HITL:
        return SESSION_STATUS_AWAITING_HITL
    return SESSION_STATUS_RUNNING


async def _pick_active_run(
    run_repo: AgentRunRepository,
    thread_id: str,
    agent_id: int,
) -> AgentRunDomain | None:
    active = await run_repo.list_active_for_thread_agent(thread_id, agent_id)
    if active:
        return active[0]
    latest = await run_repo.get_latest_for_thread_agent(thread_id, agent_id)
    if latest and latest.status in ACTIVE_AGENT_RUN_STATUSES:
        return latest
    return None


async def _response_for_active_run(
    *,
    run: AgentRunDomain,
    main_repo: MainMessageRepository,
    run_msg_repo: AgentRunMessageRepository,
    thread_id: str,
    agent_id: int,
) -> SessionStatusResponse | None:
    has_ai = await _has_ai_response(
        main_repo=main_repo,
        run_msg_repo=run_msg_repo,
        thread_id=thread_id,
        agent_id=agent_id,
        session_id=run.session_id,
    )
    has_promoted = await main_repo.has_promoted_ai_for_session(thread_id, run.session_id)
    if _is_orphan_active_run(run, has_ai=has_ai, has_promoted=has_promoted):
        return None
    return SessionStatusResponse(
        session_id=run.session_id,
        status=_session_status_for_run(run),
        has_ai_response=has_ai,
    )


class SessionStatusService:
    """Resolve polling status from agent runs, main timeline, and HITL."""

    def __init__(self, tenant_id: int, db: AsyncSession) -> None:
        self.tenant_id = tenant_id
        self.db = db

    async def resolve(self, *, thread_id: str, agent_id: int) -> SessionStatusResponse:
        main_repo = MainMessageRepository(self.db)
        run_repo = AgentRunRepository(self.db)
        run_msg_repo = AgentRunMessageRepository(self.db)
        hitl_repo = HitlApprovalRepository(self.db)

        pending_hitl = await hitl_repo.get_latest_pending_by_thread(self.tenant_id, thread_id)
        if pending_hitl:
            session_id = pending_hitl.session_id
            has_ai = await _has_ai_response(
                main_repo=main_repo,
                run_msg_repo=run_msg_repo,
                thread_id=thread_id,
                agent_id=agent_id,
                session_id=session_id,
            )
            return SessionStatusResponse(
                session_id=session_id,
                status=SESSION_STATUS_AWAITING_HITL,
                has_ai_response=has_ai,
                pending_hitl=PendingHitlInfo(
                    proposal_id=pending_hitl.proposal_id,
                    tool_name=pending_hitl.tool_name,
                    session_id=session_id,
                ),
            )

        approved_hitl = await hitl_repo.get_latest_approved_by_thread(self.tenant_id, thread_id)
        if approved_hitl and approved_hitl.approved_at:
            latest_run = await run_repo.get_latest_for_thread_agent(thread_id, agent_id)
            has_followup = latest_run is not None and (
                latest_run.created_at > approved_hitl.approved_at
                or latest_run.session_id != approved_hitl.session_id
            )
            if not has_followup and not is_stale_running_session(approved_hitl.approved_at):
                return SessionStatusResponse(
                    session_id=approved_hitl.session_id,
                    status=SESSION_STATUS_HITL_APPROVED_PENDING_CONTINUE,
                    has_ai_response=True,
                    approved_hitl=ApprovedHitlInfo(
                        proposal_id=approved_hitl.proposal_id,
                        tool_name=approved_hitl.tool_name,
                        session_id=approved_hitl.session_id,
                    ),
                )

        active_run = await _pick_active_run(run_repo, thread_id, agent_id)
        if active_run:
            active_response = await _response_for_active_run(
                run=active_run,
                main_repo=main_repo,
                run_msg_repo=run_msg_repo,
                thread_id=thread_id,
                agent_id=agent_id,
            )
            if active_response is not None:
                return active_response

        latest_run = await run_repo.get_latest_for_thread_agent(thread_id, agent_id)
        if latest_run:
            has_ai = await _has_ai_response(
                main_repo=main_repo,
                run_msg_repo=run_msg_repo,
                thread_id=thread_id,
                agent_id=agent_id,
                session_id=latest_run.session_id,
            )
            return SessionStatusResponse(status=SESSION_STATUS_COMPLETED, has_ai_response=has_ai)

        return SessionStatusResponse(status=SESSION_STATUS_COMPLETED, has_ai_response=True)


async def resolve_session_status(
    *,
    tenant_id: int,
    db: AsyncSession,
    thread_id: str,
    agent_id: int,
) -> SessionStatusResponse:
    """Functional entry point (prefer ``SessionStatusService`` in new code)."""
    return await SessionStatusService(tenant_id, db).resolve(thread_id=thread_id, agent_id=agent_id)
