"""Committed HITL checkpoint resume streaming (no pinned HTTP DB session)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.session import app_db_session
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.streaming import iter_sse_from_event_queue
from apps.tenant_app_service.hitl.resume_service import HitlResumeService
from apps.tenant_app_service.hitl.service import HitlApprovalService

logger = get_logger(__name__)


async def assert_hitl_resume_allowed(
    tenant_id: int,
    proposal_id: str,
    *,
    user_id: int,
) -> None:
    """Verify the caller may resume this proposal (short DB session)."""
    async with app_db_session() as db:
        service = HitlApprovalService(tenant_id, db)
        approval = await service.get_approval(proposal_id)
        if approval.requested_by != user_id:
            raise AuthorizationError("You are not allowed to resume this HITL proposal")


async def iter_hitl_resume_stream_committed(
    tenant_id: int,
    proposal_id: str,
    *,
    current_user: UserDTO,
) -> AsyncIterator[str]:
    """Yield SSE for checkpoint resume; agent work uses its own DB sessions."""
    event_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _background() -> None:
        try:
            async with app_db_session() as db:
                resume_service = HitlResumeService(tenant_id, db)
                async for payload in resume_service.stream_resume(
                    proposal_id,
                    current_user=current_user,
                ):
                    await event_queue.put(payload)
        except Exception:
            logger.exception("HITL resume stream failed proposal_id=%s", proposal_id)
            error_line = f"data: {json.dumps({'type': 'error', 'message': 'HITL resume failed'})}\n\n"
            await event_queue.put(error_line)
        finally:
            await event_queue.put(f"data: {json.dumps({'type': 'done'})}\n\n")
            await event_queue.put(None)

    asyncio.create_task(_background())

    async for line in iter_sse_from_event_queue(
        event_queue,
        session_id=proposal_id,
        on_client_disconnect=lambda _sid: logger.info(
            "HITL resume SSE client disconnected proposal_id=%s; agent may continue in background",
            proposal_id,
        ),
    ):
        yield line
