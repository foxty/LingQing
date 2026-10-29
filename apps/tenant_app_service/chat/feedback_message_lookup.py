"""Resolve persisted chat message IDs for ingress feedback (main + run stores)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.chat.agent_run_message_repository import AgentRunMessageRepository
from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository


async def resolve_latest_ai_message_id_for_session(
    db: AsyncSession,
    *,
    thread_id: str,
    session_id: str,
) -> str | None:
    main_repo = MainMessageRepository(db)
    promoted = await main_repo.get_latest_promoted_ai_for_session(thread_id, session_id)
    if promoted:
        return promoted.message_id

    run_repo = AgentRunMessageRepository(db)
    run_ai = await run_repo.get_latest_ai_message_for_session(thread_id, session_id)
    return run_ai.message_id if run_ai and run_ai.message_id else None


async def feedback_message_id_exists(db: AsyncSession, message_id: str) -> bool:
    main_repo = MainMessageRepository(db)
    if await main_repo.get_by_message_id_only(message_id):
        return True
    run_repo = AgentRunMessageRepository(db)
    return await run_repo.get_message_by_message_id(message_id) is not None


async def update_message_metadata_for_feedback(
    db: AsyncSession,
    *,
    message_id: str,
    metadata_patch: dict,
) -> bool:
    main_repo = MainMessageRepository(db)
    main_row = await main_repo.get_by_message_id_only(message_id)
    if main_row is not None:
        merged = dict(main_row.message_metadata or {})
        merged.update(metadata_patch)
        await main_repo.update_message_metadata(main_row, merged)
        return True

    run_repo = AgentRunMessageRepository(db)
    run_row = await run_repo.get_message_by_message_id(message_id)
    if run_row is not None:
        merged = dict(run_row.message_metadata or {})
        merged.update(metadata_patch)
        await run_repo.update_message_metadata(run_row, merged)
        return True

    return False
