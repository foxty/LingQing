"""Persist chat-only room messages on shared threads (no agent invocation)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError, ValidationError
from apps.shared.db.models import ChatMessage, ChatThread
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.thread_access import require_write_thread
from apps.tenant_app_service.chat.thread_kinds import (
    INTERACTION_ROOM_MESSAGE,
    SOURCE_SLACK_PASSIVE,
    SOURCE_WORKBENCH,
    THREAD_KIND_SHARED,
)


async def persist_room_message(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    author: UserDTO,
    content: str,
    source: str = SOURCE_WORKBENCH,
    external_metadata: dict | None = None,
    external_dedupe_key: str | None = None,
) -> ChatMessage:
    """Save a human room message without running the agent.

    When ``external_dedupe_key`` is set it is used as ``message_id`` (Slack dedupe).
    """
    stripped = (content or "").strip()
    if not stripped:
        raise ValidationError("Message content is required")

    thread = await require_write_thread(db, thread_id=thread_id, user=author)
    if thread.tenant_id != tenant_id:
        raise AuthorizationError("Tenant mismatch")
    if thread.thread_kind != THREAD_KIND_SHARED:
        raise ValidationError("Room messages are only supported on shared threads")

    message_id = external_dedupe_key or str(uuid4())
    if external_dedupe_key:
        from sqlalchemy import select

        result = await db.execute(select(ChatMessage).where(ChatMessage.message_id == message_id))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    metadata = {
        "interaction": INTERACTION_ROOM_MESSAGE,
        "source": source,
    }
    if external_metadata:
        metadata.update(external_metadata)
    row = ChatMessage(
        message_id=message_id,
        thread_id=thread_id,
        type="human",
        content=stripped,
        author_user_id=author.id,
        agent_id=None,
        session_id=None,
        timestamp=datetime.now(UTC),
        is_summarized=False,
        message_metadata=metadata,
    )
    repo = MessageRepository(db)
    saved = await repo.save_message(row)

    db_thread = await db.get(ChatThread, thread_id)
    if db_thread is not None:
        db_thread.message_count = (db_thread.message_count or 0) + 1
        await db.flush()

    return saved


async def persist_slack_passive_room_message(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    author_user_id: int,
    content: str,
    slack_user_id: str,
    slack_ts: str,
    display_name: str | None = None,
) -> ChatMessage | None:
    from apps.tenant_app_service.auth.repository import UserRepository

    user_repo = UserRepository(db)
    membership = await user_repo.get_user_membership(tenant_id, author_user_id)
    if not membership:
        return None
    user, _ = membership
    from apps.tenant_app_service.tenant.repository import TenantRepository

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    tenant_name = tenant.name if tenant else ""
    author = UserDTO(
        id=user.id,
        username=user.username,
        email=user.email or "",
        role=user.role,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
    )
    from apps.tenant_app_service.chat.compose_message import compose_thread_message

    row, _invoke = await compose_thread_message(
        db,
        tenant_id=tenant_id,
        thread_id=thread_id,
        author=author,
        content=content,
        mentions=[],
        source=SOURCE_SLACK_PASSIVE,
        external_metadata={
            "slack_user_id": slack_user_id,
            "slack_ts": slack_ts,
            "display_name": display_name,
        },
        external_dedupe_key=f"slack_passive_{slack_ts}",
    )
    return row
