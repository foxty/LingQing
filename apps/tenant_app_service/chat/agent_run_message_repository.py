"""Repository for agent_run_messages (run-scoped chat persistence)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentRunMessage, ChatMessage


class AgentRunMessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_run(self, run_id: str) -> list[AgentRunMessage]:
        result = await self.db.execute(
            select(AgentRunMessage)
            .where(AgentRunMessage.run_id == run_id)
            .order_by(AgentRunMessage.created_at.asc(), AgentRunMessage.id.asc())
        )
        return list(result.scalars().all())

    async def has_ai_for_session(self, thread_id: str, agent_id: int, session_id: str) -> bool:
        result = await self.db.execute(
            select(AgentRunMessage.id)
            .where(
                AgentRunMessage.thread_id == thread_id,
                AgentRunMessage.agent_id == agent_id,
                AgentRunMessage.session_id == session_id,
                AgentRunMessage.type == "ai",
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return True
        return False

    async def save_messages_batch(self, messages: list[AgentRunMessage]) -> None:
        if not messages:
            return
        self.db.add_all(messages)
        await self.db.flush()

    async def get_messages_by_ids(self, message_ids: list[str]) -> list[AgentRunMessage]:
        if not message_ids:
            return []
        result = await self.db.execute(
            select(AgentRunMessage).where(AgentRunMessage.message_id.in_(message_ids))
        )
        return list(result.scalars().all())

    async def get_unsummarized_messages(
        self,
        *,
        run_id: str,
        agent_id: int,
        limit: int | None = None,
    ) -> list[AgentRunMessage]:
        query = (
            select(AgentRunMessage)
            .where(
                AgentRunMessage.run_id == run_id,
                AgentRunMessage.agent_id == agent_id,
                AgentRunMessage.is_summarized.is_(False),
            )
            .order_by(AgentRunMessage.created_at.desc(), AgentRunMessage.id.desc())
        )
        if limit is not None:
            if limit <= 0:
                return []
            query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_messages_as_summarized(self, message_ids: list[str], session_summary_id: int) -> None:
        if not message_ids:
            return
        from sqlalchemy import update

        await self.db.execute(
            update(AgentRunMessage)
            .where(AgentRunMessage.message_id.in_(message_ids))
            .values(is_summarized=True)
        )

    async def get_latest_ai_message_for_session(self, thread_id: str, session_id: str) -> AgentRunMessage | None:
        result = await self.db.execute(
            select(AgentRunMessage)
            .where(
                AgentRunMessage.thread_id == thread_id,
                AgentRunMessage.session_id == session_id,
                AgentRunMessage.type == "ai",
            )
            .order_by(AgentRunMessage.created_at.desc(), AgentRunMessage.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_message_by_message_id(self, message_id: str) -> AgentRunMessage | None:
        result = await self.db.execute(
            select(AgentRunMessage).where(AgentRunMessage.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def update_message_metadata(self, message: AgentRunMessage, metadata: dict) -> None:
        message.message_metadata = metadata
        await self.db.flush()

    async def get_messages_by_session(self, session_id: str) -> list[AgentRunMessage]:
        result = await self.db.execute(
            select(AgentRunMessage)
            .where(AgentRunMessage.session_id == session_id)
            .order_by(AgentRunMessage.created_at.asc(), AgentRunMessage.id.asc())
        )
        return list(result.scalars().all())

    async def get_last_ai_message_with_tool_calls(self, run_id: str, agent_id: int) -> AgentRunMessage | None:
        result = await self.db.execute(
            select(AgentRunMessage)
            .where(
                AgentRunMessage.run_id == run_id,
                AgentRunMessage.agent_id == agent_id,
                AgentRunMessage.type == "ai",
                AgentRunMessage.tool_calls.isnot(None),
            )
            .order_by(AgentRunMessage.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None and not row.tool_calls:
            return None
        return row

    async def get_tool_message_by_call_id(
        self,
        thread_id: str,
        tool_call_id: str,
        *,
        run_id: str | None = None,
    ) -> AgentRunMessage | None:
        query = select(AgentRunMessage).where(
            AgentRunMessage.thread_id == thread_id,
            AgentRunMessage.type == "tool",
        )
        if run_id:
            query = query.where(AgentRunMessage.run_id == run_id)
        result = await self.db.execute(query)
        for row in result.scalars().all():
            kwargs = row.additional_kwargs or {}
            if kwargs.get("tool_call_id") == tool_call_id:
                return row
        return None

    async def has_ai_message_after_db_id_in_session(
        self,
        thread_id: str,
        agent_id: int,
        after_db_id: int,
        session_id: str,
    ) -> bool:
        result = await self.db.execute(
            select(AgentRunMessage.id)
            .where(
                AgentRunMessage.thread_id == thread_id,
                AgentRunMessage.agent_id == agent_id,
                AgentRunMessage.session_id == session_id,
                AgentRunMessage.type == "ai",
                AgentRunMessage.id > after_db_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_messages_from_db_id(
        self,
        *,
        run_id: str,
        agent_id: int,
        from_db_id: int,
    ) -> list[AgentRunMessage]:
        result = await self.db.execute(
            select(AgentRunMessage)
            .where(
                AgentRunMessage.run_id == run_id,
                AgentRunMessage.agent_id == agent_id,
                AgentRunMessage.id >= from_db_id,
            )
            .order_by(AgentRunMessage.created_at.asc(), AgentRunMessage.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def as_chat_message_shim(row: AgentRunMessage) -> ChatMessage:
        """Deprecated: use ``agent_run_message_to_chat_message`` in message_persistence_adapters."""
        from apps.tenant_app_service.agents.message_persistence_adapters import agent_run_message_to_chat_message

        return agent_run_message_to_chat_message(row)
