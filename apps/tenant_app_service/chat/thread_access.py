"""Access checks for personal and shared chat threads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.models import ChatThread
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.membership_repository import ThreadMembershipRepository
from apps.tenant_app_service.chat.thread_kinds import (
    MEMBER_ROLE_MEMBER,
    MEMBER_ROLE_OWNER,
    MEMBER_ROLE_VIEWER,
    THREAD_KIND_PERSONAL,
)


async def get_thread_row(db: AsyncSession, thread_id: str) -> ChatThread | None:
    return await db.get(ChatThread, thread_id)


async def _user_membership(db: AsyncSession, thread_id: str, user_id: int):
    return await ThreadMembershipRepository(db).get_user_member(thread_id, user_id)


async def can_read_thread(db: AsyncSession, *, thread: ChatThread, user: UserDTO) -> bool:
    if thread.tenant_id != user.tenant_id:
        return False
    membership = await _user_membership(db, thread.id, user.id)
    if membership is not None:
        return True
    return thread.thread_kind == THREAD_KIND_PERSONAL and thread.user_id == user.id


async def can_write_thread(db: AsyncSession, *, thread: ChatThread, user: UserDTO) -> bool:
    if thread.tenant_id != user.tenant_id:
        return False
    membership = await _user_membership(db, thread.id, user.id)
    if membership is not None:
        return membership.role in {MEMBER_ROLE_OWNER, MEMBER_ROLE_MEMBER}
    return thread.thread_kind == THREAD_KIND_PERSONAL and thread.user_id == user.id


async def can_link_artifact(db: AsyncSession, *, thread: ChatThread, user: UserDTO) -> bool:
    return await can_write_thread(db, thread=thread, user=user)


async def require_read_thread(db: AsyncSession, *, thread_id: str, user: UserDTO) -> ChatThread:
    thread = await get_thread_row(db, thread_id)
    if thread is None:
        raise AuthorizationError(f"Thread {thread_id} not found")
    if not await can_read_thread(db, thread=thread, user=user):
        raise AuthorizationError("Access denied")
    return thread


async def require_write_thread(db: AsyncSession, *, thread_id: str, user: UserDTO) -> ChatThread:
    thread = await get_thread_row(db, thread_id)
    if thread is None:
        raise AuthorizationError(f"Thread {thread_id} not found")
    if not await can_write_thread(db, thread=thread, user=user):
        raise AuthorizationError("Access denied")
    return thread


def is_viewer_only(role: str) -> bool:
    return role == MEMBER_ROLE_VIEWER


async def assert_owner_can_link_artifact(db: AsyncSession, *, thread: ChatThread, owner_id: int) -> None:
    """Artifact link guard for thread owner or non-viewer member."""
    membership = await _user_membership(db, thread.id, owner_id)
    if membership is not None:
        if is_viewer_only(membership.role):
            raise AuthorizationError("Access denied")
        return
    if thread.user_id != owner_id:
        raise AuthorizationError("Access denied")
