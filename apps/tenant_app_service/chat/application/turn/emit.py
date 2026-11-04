"""Background SSE emit for prepared stream turns."""

from __future__ import annotations

import asyncio
import json

from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.schemas import ChatRequest
from apps.tenant_app_service.chat.streaming import PreparedChatStream, user_stream_error_sse_payload


async def emit_prepared_agent_stream(
    tenant_id: int,
    *,
    event_queue: asyncio.Queue[str | None],
    request: ChatRequest,
    current_user: UserDTO,
    prepared: PreparedChatStream,
    access_token: str | None = None,
) -> None:
    """Push SSE for a prepared stream turn without pinning a DB session for the graph."""
    from apps.tenant_app_service.chat.turn_db import turn_service_session

    logger = get_logger("ChatTurnService")
    session_id = prepared.session_id
    run_cancelled = False

    async def _is_cancelled(run_id: str | None) -> bool:
        if not run_id:
            return False
        async with turn_service_session(tenant_id) as svc:
            return await svc._run_is_cancelled_in_db(run_id)

    try:
        async with turn_service_session(tenant_id) as svc:
            stream = svc.run_stream_turn(
                request=request,
                current_user=current_user,
                session_id=session_id,
                agent_id=prepared.agent_id,
                agent_name=prepared.agent_name,
                access_token=access_token,
                initial_messages=prepared.initial_messages,
                run_id=prepared.run_id,
                trigger_message_id=prepared.trigger_message_id,
                invoke_index=prepared.invoke_index,
                ephemeral_graph=True,
            )
        async for payload in stream:
            await event_queue.put(payload)
    except asyncio.CancelledError:
        if prepared.run_id and await _is_cancelled(prepared.run_id):
            run_cancelled = True
        else:
            raise
    except Exception as exc:
        logger.error(
            "Background agent run failed for session %s: %s",
            session_id,
            exc,
            exc_info=True,
        )
        error_data = user_stream_error_sse_payload(exc)
        await event_queue.put(f"data: {json.dumps(error_data)}\n\n")
    finally:
        try:
            if run_cancelled or (prepared.run_id and await _is_cancelled(prepared.run_id)):
                cancelled_data = {
                    "type": "cancelled",
                    "session_id": session_id,
                    "run_id": prepared.run_id,
                }
                await event_queue.put(f"data: {json.dumps(cancelled_data)}\n\n")
        except Exception:
            logger.exception(
                "Failed cancel-status check for session %s run_id=%s",
                session_id,
                prepared.run_id,
            )
        done_data = {"type": "done", "session_id": session_id}
        await event_queue.put(f"data: {json.dumps(done_data)}\n\n")
        await event_queue.put(None)
