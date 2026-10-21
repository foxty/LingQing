"""Agent selection validation for shared thread turns."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ValidationError
from apps.shared.db.models import ChatThread
from apps.tenant_app_service.chat.membership_repository import ThreadMembershipRepository
from apps.tenant_app_service.chat.thread_kinds import THREAD_KIND_SHARED


async def validate_shared_agent_turn(
    db: AsyncSession,
    *,
    thread: ChatThread,
    agent_id: int,
) -> None:
    if thread.thread_kind != THREAD_KIND_SHARED:
        return
    roster = ThreadMembershipRepository(db)
    if await roster.get_agent_member(thread.id, agent_id) is None:
        raise ValidationError(f"Agent {agent_id} is not on this shared thread roster")


async def resolve_required_agent_for_shared(
    db: AsyncSession,
    *,
    thread: ChatThread,
    requested_agent_id: int,
) -> int:
    """Validate roster membership; return agent_id to run."""
    await validate_shared_agent_turn(db, thread=thread, agent_id=requested_agent_id)
    return requested_agent_id
