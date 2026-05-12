"""Session status resolution for durable chat polling."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.chat.domain import (
    SESSION_STALE_RUNNING_SECONDS,
    SESSION_STATUS_AWAITING_HITL,
    SESSION_STATUS_COMPLETED,
    SESSION_STATUS_HITL_APPROVED_PENDING_CONTINUE,
    SESSION_STATUS_RUNNING,
)
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.schemas import (
    ApprovedHitlInfo,
    PendingHitlInfo,
    SessionStatusResponse,
)
from apps.tenant_app_service.hitl.repository import HitlApprovalRepository


def _is_stale_session(
    started_at: datetime | None,
    *,
    stale_after_seconds: int = SESSION_STALE_RUNNING_SECONDS,
    now: datetime | None = None,
) -> bool:
    if started_at is None:
        return False

    current = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return current - started_at > timedelta(seconds=stale_after_seconds)


async def resolve_session_status(
    *,
    tenant_id: int,
    db: AsyncSession,
    message_repo: MessageRepository,
    thread_id: str,
    agent_id: int,
) -> SessionStatusResponse:
    """Return durable session status from chat messages and HITL state."""
    hitl_repo = HitlApprovalRepository(db)
    pending_hitl = await hitl_repo.get_latest_pending_by_thread(tenant_id, thread_id)
    if pending_hitl:
        has_ai = False
        if pending_hitl.session_id:
            has_ai = await message_repo.has_ai_message_for_session(
                thread_id,
                agent_id,
                pending_hitl.session_id,
            )
        return SessionStatusResponse(
            session_id=pending_hitl.session_id,
            status=SESSION_STATUS_AWAITING_HITL,
            has_ai_response=has_ai,
            pending_hitl=PendingHitlInfo(
                proposal_id=pending_hitl.proposal_id,
                tool_name=pending_hitl.tool_name,
                session_id=pending_hitl.session_id,
            ),
        )

    approved_hitl = await hitl_repo.get_latest_approved_by_thread(tenant_id, thread_id)
    if approved_hitl and approved_hitl.approved_at:
        has_followup = await message_repo.has_messages_after_timestamp(
            thread_id,
            agent_id,
            approved_hitl.approved_at,
            exclude_session_id=approved_hitl.session_id,
        )
        if not has_followup:
            if not _is_stale_session(approved_hitl.approved_at):
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

    latest_human = await message_repo.get_latest_human_message(thread_id, agent_id)
    if latest_human and latest_human.session_id:
        session_id = latest_human.session_id
        has_ai = await message_repo.has_ai_message_for_session(thread_id, agent_id, session_id)
        if not has_ai:
            if _is_stale_session(latest_human.created_at):
                return SessionStatusResponse(
                    session_id=session_id,
                    status=SESSION_STATUS_COMPLETED,
                    has_ai_response=False,
                )
            return SessionStatusResponse(
                session_id=session_id,
                status=SESSION_STATUS_RUNNING,
                has_ai_response=False,
            )

    return SessionStatusResponse(status=SESSION_STATUS_COMPLETED, has_ai_response=True)
