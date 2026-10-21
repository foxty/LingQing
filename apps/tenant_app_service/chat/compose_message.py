"""Unified thread message compose: human persist + which agents to invoke."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError, ValidationError
from apps.shared.db.models import ChatMessage, ChatThread
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.membership_repository import ThreadMembershipRepository
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.thread_access import require_write_thread
from apps.tenant_app_service.chat.thread_kinds import (
    INTERACTION_AGENT_TURN,
    INTERACTION_ROOM_MESSAGE,
    SOURCE_WORKBENCH,
    THREAD_KIND_PERSONAL,
    THREAD_KIND_SHARED,
)


def resolve_invoke_agent_ids(
    *,
    thread: ChatThread,
    mention_agent_ids: list[int],
    roster_agent_ids: set[int],
) -> list[int]:
    """Decide which agents to run for this compose (order preserved, deduped)."""
    if thread.thread_kind == THREAD_KIND_PERSONAL:
        if mention_agent_ids:
            return _filter_roster_agents(mention_agent_ids, roster_agent_ids)
        primary = thread.agent_id
        return [primary] if primary in roster_agent_ids or not roster_agent_ids else [primary]

    # Shared: room-only when no agent mentions; otherwise invoke all mentioned agents.
    if not mention_agent_ids:
        return []
    return _filter_roster_agents(mention_agent_ids, roster_agent_ids)


def _filter_roster_agents(agent_ids: list[int], roster: set[int]) -> list[int]:
    if not roster:
        return list(dict.fromkeys(agent_ids))
    seen: set[int] = set()
    ordered: list[int] = []
    for aid in agent_ids:
        if aid not in roster:
            continue
        if aid in seen:
            continue
        seen.add(aid)
        ordered.append(aid)
    return ordered


async def persist_compose_human_message(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    author: UserDTO,
    content: str,
    mentions: list[dict],
    attached_artifact_ids: list[int] | None = None,
    source: str = SOURCE_WORKBENCH,
    external_metadata: dict | None = None,
    external_dedupe_key: str | None = None,
) -> ChatMessage:
    """Save one visible human message for personal or shared threads."""
    stripped = (content or "").strip()
    if not stripped:
        raise ValidationError("Message content is required")

    thread = await require_write_thread(db, thread_id=thread_id, user=author)
    if thread.tenant_id != tenant_id:
        raise AuthorizationError("Tenant mismatch")

    message_id = external_dedupe_key or str(uuid4())
    if external_dedupe_key:
        from sqlalchemy import select

        result = await db.execute(select(ChatMessage).where(ChatMessage.message_id == message_id))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    metadata: dict = {
        "interaction": INTERACTION_ROOM_MESSAGE,
        "source": source,
        "mentions": mentions,
    }
    if attached_artifact_ids:
        metadata["attached_artifact_ids"] = attached_artifact_ids
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


async def roster_agent_ids_for_thread(db: AsyncSession, thread_id: str) -> set[int]:
    membership = ThreadMembershipRepository(db)
    agents = await membership.list_agent_members(thread_id)
    if agents:
        return {a.agent_id for a in agents}
    thread = await db.get(ChatThread, thread_id)
    if thread is None:
        return set()
    return {thread.agent_id}


async def compose_thread_message(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    author: UserDTO,
    content: str,
    mentions: list[dict],
    attached_artifact_ids: list[int] | None = None,
    source: str = SOURCE_WORKBENCH,
    external_metadata: dict | None = None,
    external_dedupe_key: str | None = None,
) -> tuple[ChatMessage, list[int]]:
    """Persist human message and return agent ids to invoke (0..N)."""
    thread = await require_write_thread(db, thread_id=thread_id, user=author)
    roster = await roster_agent_ids_for_thread(db, thread_id)
    mention_agent_ids = [int(m["id"]) for m in mentions if m.get("type") == "agent"]

    invoke_ids = resolve_invoke_agent_ids(
        thread=thread,
        mention_agent_ids=mention_agent_ids,
        roster_agent_ids=roster,
    )

    if thread.thread_kind == THREAD_KIND_SHARED and invoke_ids:
        for aid in invoke_ids:
            if aid not in roster:
                raise ValidationError(f"Agent {aid} is not on this conversation roster")

    interaction = INTERACTION_AGENT_TURN if invoke_ids else INTERACTION_ROOM_MESSAGE
    saved = await persist_compose_human_message(
        db,
        tenant_id=tenant_id,
        thread_id=thread_id,
        author=author,
        content=content,
        mentions=mentions,
        attached_artifact_ids=attached_artifact_ids,
        source=source,
        external_metadata={**(external_metadata or {}), "interaction": interaction},
        external_dedupe_key=external_dedupe_key,
    )
    return saved, invoke_ids
