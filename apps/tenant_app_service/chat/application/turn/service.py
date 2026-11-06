"""Session-scoped chat turn use case — composed from prepare / stream / complete modules."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.application.turn.prepare_complete import ChatTurnPrepareCompleteMixin
from apps.tenant_app_service.chat.application.turn.runtime import ChatTurnRuntimeMixin
from apps.tenant_app_service.chat.application.turn.session import ChatTurnSessionMixin
from apps.tenant_app_service.chat.application.turn.stream_turn import StreamTurnUseCase
from apps.tenant_app_service.chat.application.turn.turn_helpers import ChatTurnHelpersMixin
from apps.tenant_app_service.chat.schemas import ChatRequest
from apps.tenant_app_service.chat.service_base import ChatServiceBase
from apps.tenant_app_service.chat.streaming import PreparedChatStream


class ChatTurnService(
    ChatTurnHelpersMixin,
    ChatTurnRuntimeMixin,
    ChatTurnSessionMixin,
    ChatTurnPrepareCompleteMixin,
    ChatServiceBase,
):
    """Prepare, invoke, and complete agent turns within one database session."""

    def __init__(self, tenant_id: int, db: AsyncSession) -> None:
        super().__init__(tenant_id, db)
        self._stream_turn = StreamTurnUseCase(self)

    async def _finish_graph_stream(self, *args, **kwargs) -> None:
        await self._stream_turn.finish_graph_stream(*args, **kwargs)

    async def _run_is_cancelled_in_db(self, run_id: str | None) -> bool:
        return await self._stream_turn.run_is_cancelled_in_db(run_id)

    async def run_stream_turn(self, **kwargs) -> AsyncIterator[str]:
        async for line in self._stream_turn.run_stream_turn(**kwargs):
            yield line

    async def run_hitl_checkpoint_resume_stream(self, **kwargs) -> AsyncIterator[str]:
        async for line in self._stream_turn.run_hitl_checkpoint_resume_stream(**kwargs):
            yield line

    async def run_agent_and_emit_prepared(
        self,
        *,
        event_queue,
        request: ChatRequest,
        current_user: UserDTO,
        prepared: PreparedChatStream,
        access_token: str | None = None,
    ) -> None:
        await self._stream_turn.run_agent_and_emit_prepared(
            event_queue=event_queue,
            request=request,
            current_user=current_user,
            prepared=prepared,
            access_token=access_token,
        )
