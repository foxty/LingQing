"""Message repository for chat module.

Provides CRUD operations and summarization helpers for chat messages.
Shared between ConversationMemoryManager (agent use) and ChatService (raw message retrieval).
"""

from datetime import datetime
from typing import List

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatMessage, ChatThread
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.domain import MESSAGE_TYPE_AI, MESSAGE_TYPE_HUMAN

logger = get_logger(__name__)


class MessageRepository:
    """Repository for message operations with summarization support."""

    def __init__(self, db: AsyncSession):
        """Initialize repository.

        Args:
            db: Database session
        """
        self.db = db

    async def save_message(self, message: ChatMessage) -> ChatMessage:
        """Save a single message.

        Args:
            message: ChatMessage to save

        Returns:
            Saved message
        """
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def save_messages_batch(self, messages: List[ChatMessage]) -> None:
        """Save multiple messages in a batch.

        Args:
            messages: List of ChatMessage models to save
        """
        if not messages:
            return

        self.db.add_all(messages)
        await self.db.commit()

        logger.debug(f"Saved {len(messages)} messages in batch")

    async def mark_messages_as_summarized(self, message_ids: List[str], summary_id: int) -> int:
        """Mark messages as summarized using a single bulk UPDATE.

        Args:
            message_ids: List of message IDs to mark
            summary_id: ID of the summary (for logging)

        Returns:
            Number of messages updated
        """
        if not message_ids:
            return 0

        from sqlalchemy import update

        stmt = update(ChatMessage).where(ChatMessage.message_id.in_(message_ids)).values(is_summarized=True)
        result = await self.db.execute(stmt)
        await self.db.flush()

        count = result.rowcount
        logger.info(f"Marked {count} messages as summarized (summary_id={summary_id})")
        return count

    async def get_message_count(self, thread_id: str) -> int:
        """Get message count for a thread.

        Uses indexed query for high performance.

        Args:
            thread_id: Thread ID

        Returns:
            Message count
        """
        from sqlalchemy import func

        query = select(func.count(ChatMessage.id)).where(ChatMessage.thread_id == thread_id)

        result = await self.db.execute(query)
        count = result.scalar()

        return count or 0

    async def increment_thread_message_count(self, thread_id: str, increment: int = 1) -> None:
        """Increment message count for a thread.

        Args:
            thread_id: Thread ID
            increment: Number to increment by
        """
        thread = await self.db.get(ChatThread, thread_id)
        if thread:
            thread.message_count += increment
            await self.db.commit()

    async def get_messages_by_ids(self, message_ids: List[str]) -> List[ChatMessage]:
        """Get messages by their IDs.

        Args:
            message_ids: List of message IDs

        Returns:
            List of ChatMessage models
        """
        if not message_ids:
            return []

        query = select(ChatMessage).where(ChatMessage.message_id.in_(message_ids))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_messages_by_thread(self, thread_id: str) -> List[ChatMessage]:
        """Get all messages from a thread (for capability execution details).

        Args:
            thread_id: thread ID
        Returns:
            List of ChatMessage models ordered by (created_at, id) ASC
        """
        query = (
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )

        result = await self.db.execute(query)
        messages = list(result.scalars().all())

        logger.debug(f"Fetched {len(messages)} messages for sub-agent thread {thread_id}")
        return messages

    async def get_messages_by_session(self, session_id: str) -> List[ChatMessage]:
        """Get all messages for a specific session.

        Args:
            session_id: Session ID stored in message_metadata

        Returns:
            List of messages ordered by (created_at, id) ASC
        """
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )

        result = await self.db.execute(query)
        messages = list(result.scalars().all())

        logger.debug(f"Found {len(messages)} messages for session {session_id}")

        return messages

    async def get_messages_by_agent(
        self,
        thread_id: str,
        agent_id: int,
        session_id: str | None = None,
        limit: int | None = None,
        before_created_at: datetime | None = None,
        before_id: int | None = None,
        include_tool_messages: bool = True,
    ) -> List[ChatMessage]:
        """Get messages for a specific agent in a thread.

        Used for agent context isolation (e.g., sub-agents see only their messages).

        Args:
            thread_id: Thread ID
            agent_id: Agent ID
            limit: Optional limit on number of messages (most recent)

        Returns:
            List of ChatMessage models ordered by (created_at, id) DESC (most recent first).
            Caller should reverse if ASC order is needed.
        """
        where = [ChatMessage.thread_id == thread_id, ChatMessage.agent_id == agent_id]
        if not include_tool_messages:
            where.append(ChatMessage.type != "tool")
        if session_id is not None:
            where.append(ChatMessage.session_id == session_id)
        if before_created_at and before_id:
            where.append(
                or_(
                    ChatMessage.created_at < before_created_at,
                    and_(ChatMessage.created_at == before_created_at, ChatMessage.id < before_id),
                )
            )
        elif before_created_at:
            where.append(ChatMessage.created_at < before_created_at)
        elif before_id:
            where.append(ChatMessage.id < before_id)
        query = select(ChatMessage).where(*where).order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())

        if limit is not None:
            query = query.limit(limit)

        result = await self.db.execute(query)
        messages = list(result.scalars().all())

        logger.debug(
            f"Fetched {len(messages)} messages for thread {thread_id}, agent {agent_id} "
            f"(limit={limit if limit is not None else 'all'})"
        )
        return messages

    async def get_messages_by_session_window(
        self,
        thread_id: str,
        agent_id: int,
        session_limit: int,
        before_session_id: str | None = None,
        include_tool_messages: bool = True,
        session_id: str | None = None,
    ) -> tuple[List[ChatMessage], bool, str | None]:
        """Get complete messages for a window of sessions.

        Returns all messages belonging to the most recent `session_limit` sessions.
        Session pagination uses `before_session_id` as cursor.
        """
        if session_limit <= 0:
            return [], False, None

        base_where = [ChatMessage.thread_id == thread_id, ChatMessage.agent_id == agent_id]
        if not include_tool_messages:
            base_where.append(ChatMessage.type != "tool")

        # Explicit session lookup keeps old behavior for filtered history views.
        if session_id is not None:
            query = (
                select(ChatMessage)
                .where(*base_where, ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            )
            result = await self.db.execute(query)
            return list(result.scalars().all()), False, None

        session_where = [*base_where, ChatMessage.session_id.isnot(None)]

        if before_session_id:
            cursor_stmt = select(func.max(ChatMessage.id)).where(
                *session_where, ChatMessage.session_id == before_session_id
            )
            cursor_result = await self.db.execute(cursor_stmt)
            cursor_session_end_id = cursor_result.scalar()
            if cursor_session_end_id is None:
                return [], False, None
            session_where.append(ChatMessage.id < cursor_session_end_id)
            session_where.append(ChatMessage.session_id != before_session_id)

        session_stmt = (
            select(ChatMessage.session_id, func.max(ChatMessage.id).label("session_end_id"))
            .where(*session_where)
            .group_by(ChatMessage.session_id)
            .order_by(func.max(ChatMessage.id).desc())
            .limit(session_limit + 1)
        )
        session_result = await self.db.execute(session_stmt)
        session_rows = list(session_result.all())

        if not session_rows:
            return [], False, None

        has_more = len(session_rows) > session_limit
        selected_rows = session_rows[:session_limit]
        session_ids = [row[0] for row in selected_rows if row[0]]

        if not session_ids:
            return [], has_more, None

        messages_stmt = (
            select(ChatMessage)
            .where(*base_where, ChatMessage.session_id.in_(session_ids))
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        messages_result = await self.db.execute(messages_stmt)
        messages = list(messages_result.scalars().all())
        next_before_session_id = selected_rows[-1][0] if selected_rows else None

        logger.debug(
            "Fetched %s messages across %s sessions for thread %s, agent %s",
            len(messages),
            len(session_ids),
            thread_id,
            agent_id,
        )
        return messages, has_more, next_before_session_id

    async def update_message_fields(
        self,
        message: ChatMessage,
        *,
        content: str,
        additional_kwargs: dict,
    ) -> None:
        """Update persisted message content and additional kwargs."""
        message.content = content
        message.additional_kwargs = additional_kwargs
        await self.db.flush()

    async def get_message_by_message_id(self, message_id: str) -> ChatMessage | None:
        """Get a chat message by LangChain message_id."""
        result = await self.db.execute(select(ChatMessage).where(ChatMessage.message_id == message_id))
        return result.scalar_one_or_none()

    async def get_latest_ai_message_for_session(self, thread_id: str, session_id: str) -> ChatMessage | None:
        """Get the most recent AI message for a session."""
        result = await self.db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.session_id == session_id,
                ChatMessage.type == MESSAGE_TYPE_AI,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_message_metadata(self, message: ChatMessage, metadata: dict) -> None:
        """Replace message_metadata for a persisted message."""
        message.message_metadata = metadata
        await self.db.flush()

    async def get_tool_message_by_call_id(
        self,
        thread_id: str,
        tool_call_id: str,
        session_id: str | None = None,
    ) -> ChatMessage | None:
        """Get a single tool message by tool_call_id.

        Args:
            thread_id: Thread ID
            tool_call_id: Tool call ID stored in additional_kwargs.tool_call_id
            session_id: Optional session ID filter

        Returns:
            Matching ChatMessage or None
        """
        where = [ChatMessage.thread_id == thread_id, ChatMessage.type == "tool"]
        if session_id is not None:
            where.append(ChatMessage.session_id == session_id)

        query = select(ChatMessage).where(*where).order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        result = await self.db.execute(query)
        messages = list(result.scalars().all())

        for message in messages:
            additional_kwargs = message.additional_kwargs or {}
            if additional_kwargs.get("tool_call_id") == tool_call_id:
                return message

        return None

    async def get_unsummarized_messages(
        self,
        thread_id: str,
        agent_id: int,
        limit: int | None = None,
    ) -> List[ChatMessage]:
        """Get messages that have not been summarized yet, most recent first.

        Args:
            thread_id: Thread ID
            agent_id: Agent ID
            limit: Optional cap on number of messages (most recent N)

        Returns:
            List of ChatMessage ordered by (created_at, id) DESC.
            Caller should reverse for ASC chronological order.
        """
        query = (
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.is_summarized == False,  # noqa: E712
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        logger.debug(f"Fetched {len(messages)} unsummarized messages for thread {thread_id}, agent {agent_id}")
        return messages

    async def has_ai_message_after_db_id(
        self,
        thread_id: str,
        agent_id: int,
        after_db_id: int,
    ) -> bool:
        """Return True when an AI message exists after the given database row ID."""
        stmt = (
            select(func.count(ChatMessage.id))
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.type == MESSAGE_TYPE_AI,
                ChatMessage.id > after_db_id,
            )
        )
        result = await self.db.execute(stmt)
        return (result.scalar() or 0) > 0

    async def has_ai_message_after_db_id_in_session(
        self,
        thread_id: str,
        agent_id: int,
        after_db_id: int,
        session_id: str,
    ) -> bool:
        """Return True when an AI message in the same session follows the given row ID."""
        stmt = (
            select(func.count(ChatMessage.id))
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.session_id == session_id,
                ChatMessage.type == MESSAGE_TYPE_AI,
                ChatMessage.id > after_db_id,
            )
        )
        result = await self.db.execute(stmt)
        return (result.scalar() or 0) > 0

    async def get_last_ai_message_with_tool_calls(
        self,
        thread_id: str,
        agent_id: int,
    ) -> ChatMessage | None:
        """Get the most recent AI message that has tool_calls.

        Used to ensure HITL continuity regardless of summarization state.

        Args:
            thread_id: Thread ID
            agent_id: Agent ID

        Returns:
            Most recent ChatMessage of type 'ai' with non-empty tool_calls, or None
        """
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.type == MESSAGE_TYPE_AI,
                ChatMessage.tool_calls.isnot(None),
                ChatMessage.tool_calls[0].isnot(None),
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_human_message(self, thread_id: str, agent_id: int) -> ChatMessage | None:
        """Get the most recent human message for a thread/agent."""
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.type == MESSAGE_TYPE_HUMAN,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def has_ai_message_for_session(self, thread_id: str, agent_id: int, session_id: str) -> bool:
        """Return True when an AI message exists for the given session."""
        stmt = (
            select(func.count(ChatMessage.id))
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.session_id == session_id,
                ChatMessage.type == MESSAGE_TYPE_AI,
            )
        )
        result = await self.db.execute(stmt)
        return (result.scalar() or 0) > 0

    async def has_messages_after_timestamp(
        self,
        thread_id: str,
        agent_id: int,
        after: datetime,
        *,
        exclude_session_id: str | None = None,
    ) -> bool:
        """Return True when any message exists after the given timestamp."""
        where = [
            ChatMessage.thread_id == thread_id,
            ChatMessage.agent_id == agent_id,
            ChatMessage.created_at > after,
        ]
        if exclude_session_id:
            where.append(ChatMessage.session_id != exclude_session_id)
        stmt = select(func.count(ChatMessage.id)).where(*where)
        result = await self.db.execute(stmt)
        return (result.scalar() or 0) > 0

    async def get_messages_from_db_id(
        self,
        thread_id: str,
        agent_id: int,
        from_db_id: int,
    ) -> List[ChatMessage]:
        """Get all messages starting from (inclusive) a given database row ID.

        Used to load the HITL tail block when the anchor AI message was cut off.

        Args:
            thread_id: Thread ID
            agent_id: Agent ID
            from_db_id: Inclusive lower bound on ChatMessage.id

        Returns:
            List of ChatMessage ordered by (created_at, id) ASC
        """
        query = (
            select(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.agent_id == agent_id,
                ChatMessage.id >= from_db_id,
            )
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        logger.debug(f"Fetched {len(messages)} messages from db_id>={from_db_id} for thread {thread_id}")
        return messages
