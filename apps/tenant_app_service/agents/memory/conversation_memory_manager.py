"""Conversation memory manager for optimized message storage and retrieval.

This module provides efficient message management with:
- Independent message storage in chat_messages table
- LangChain message format conversion
- Automatic conversation summarization
- Token-based context management
"""

import json
from datetime import UTC, datetime

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatMessage, ChatThread
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.message_content import normalize_message_content


def _db_message_to_langchain(db_msg: ChatMessage) -> BaseMessage:
    """Convert database message to LangChain message.

    Args:
        db_msg: Database message model

    Returns:
        Corresponding LangChain message
    """
    logger = get_logger(__name__)

    # Use message_id if available, otherwise use database id as string
    message_id = db_msg.message_id if db_msg.message_id else str(db_msg.id)
    content = db_msg.content

    # Merge metadata into additional_kwargs for backward compatibility
    # LangChain messages expect all context in additional_kwargs
    additional_kwargs = db_msg.additional_kwargs or {}
    if db_msg.message_metadata:
        additional_kwargs = {**additional_kwargs}
        ts = db_msg.timestamp
        if ts.tzinfo is None:
            # Localize naive datetime to UTC
            ts = ts.replace(tzinfo=UTC)
        else:
            # Convert to UTC if not already
            ts = ts.astimezone(UTC)
        additional_kwargs["timestamp"] = ts.isoformat()

    if db_msg.type == "human":
        return HumanMessage(id=message_id, content=content, additional_kwargs=additional_kwargs)
    elif db_msg.type == "ai":
        # Load tool_calls from dedicated field (only pass if not None/empty)
        ai_kwargs = {"id": message_id, "content": content, "additional_kwargs": additional_kwargs}
        if db_msg.tool_calls:
            ai_kwargs["tool_calls"] = db_msg.tool_calls
        return AIMessage(**ai_kwargs)
    elif db_msg.type == "system":
        return SystemMessage(id=message_id, content=content, additional_kwargs=additional_kwargs)
    elif db_msg.type == "tool":
        # ToolMessage requires tool_call_id (stored in additional_kwargs)
        tool_call_id = db_msg.additional_kwargs.get("tool_call_id") if db_msg.additional_kwargs else None
        if not tool_call_id:
            logger.warning(
                f"ToolMessage {message_id} missing tool_call_id in additional_kwargs. "
                f"This should not happen in normal operation."
            )
            # Fallback: use message id as tool_call_id (last resort)
            tool_call_id = message_id
        return ToolMessage(
            id=message_id,
            content=content,
            tool_call_id=tool_call_id,
            additional_kwargs=additional_kwargs,
        )
    else:
        logger.warning(f"Unknown message type: {db_msg.type}, defaulting to HumanMessage")
        return HumanMessage(id=message_id, content=content, additional_kwargs=additional_kwargs)


def _serialize_additional_kwargs(kwargs: dict | None) -> dict | None:
    """Serialize additional_kwargs for JSON storage, converting non-serializable objects.

    Recursively cleans the entire kwargs dict to ensure JSON compatibility:
    - Normalizes empty 'arguments' strings to '{}' (for tool_calls)
    - Converts non-serializable objects to strings
    - Handles nested dicts and lists

    Args:
        kwargs: The additional_kwargs dictionary to serialize

    Returns:
        A JSON-serializable dictionary
    """
    if not kwargs:
        return kwargs

    return _ensure_json_serializable(kwargs)


def _ensure_json_serializable(value):
    """Recursively ensure a value is JSON-serializable.

    Handles:
    - Empty 'arguments' string -> normalize to '{}' (for tool_calls)
    - Non-serializable objects -> convert to string
    - Nested structures -> recursive cleaning

    Args:
        value: Any Python value to make JSON-serializable

    Returns:
        JSON-serializable version of the value
    """
    # Handle None
    if value is None:
        return None

    # Handle dicts recursively
    if isinstance(value, dict):
        cleaned = {}
        for key, val in value.items():
            # Special case: normalize empty 'arguments' to valid JSON
            if key == "arguments" and val == "":
                cleaned[key] = "{}"
            else:
                cleaned[key] = _ensure_json_serializable(val)
        return cleaned

    # Handle lists recursively
    if isinstance(value, list):
        return [_ensure_json_serializable(item) for item in value]

    # Handle primitives - try to serialize, convert to string if fails
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class ConversationMemoryManager:
    """Manages conversation messages with optimized storage and retrieval.

    Features:
    - Load/save messages with LangChain format conversion
    - Automatic summarization when token limit exceeded
    - Smart loading: latest summary + unsummarized messages
    - Internal caching for performance optimization
    """

    def __init__(
        self,
        db_session: AsyncSession,
        thread_id: str,
        tenant_id: int,
        agent_id: int,
    ):
        """Initialize memory manager.

        Args:
            db_session: Database session for message operations
            thread_id: Thread ID for this conversation
            tenant_id: Tenant ID for mini-agent service
            agent_id: Agent ID for context isolation
        """
        self.db = db_session
        self.thread_id = thread_id
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.logger = get_logger(__name__)
        # Lazy import to avoid circular dependency
        from apps.tenant_app_service.chat.message_repository import MessageRepository

        self.message_repo = MessageRepository(db_session)
        self._mini_agent_service = None  # Lazy load when needed

        self.logger.info(
            f"Initialized ConversationMemoryManager for thread {thread_id} (tenant_id={tenant_id}, agent_id={agent_id})"
        )

    def _extract_message_timestamp(self, kwargs: dict) -> datetime:
        """Extract and parse message timestamp from kwargs, with fallback to current time.

        Removes 'timestamp' from kwargs if present.

        Priority:
        1. If timestamp exists in kwargs:
           - Parse as datetime if string (ISO 8601 format)
           - Return as-is if already datetime
        2. Fallback to current UTC time

        Args:
            kwargs: Message additional_kwargs dict (will be modified to remove 'timestamp')

        Returns:
            Parsed datetime object (UTC)
        """
        timestamp_value = kwargs.get("timestamp", None)

        if not timestamp_value:
            return datetime.now(UTC)

        # If already a datetime object, return as-is
        if isinstance(timestamp_value, datetime):
            return timestamp_value

        # If string, try to parse as ISO 8601
        if isinstance(timestamp_value, str):
            try:
                return datetime.fromisoformat(timestamp_value)
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid timestamp format: {timestamp_value}, using current time")
                return datetime.now(UTC)

        # Unexpected type, use current time
        self.logger.warning(f"Unexpected timestamp type: {type(timestamp_value)}, using current time")
        return datetime.now(UTC)

    def _extract_message_metadata(self, kwargs: dict, cap_context: dict) -> dict:
        """Extract message metadata from kwargs and capability context.

        Removes metadata keys from kwargs and merges with capability context.

        Args:
            kwargs: Message additional_kwargs dict (will be modified to remove metadata keys)
            cap_context: Capability call context from runtime config

        Returns:
            Extracted metadata dictionary
        """
        metadata = {}

        # Move metadata from additional_kwargs to metadata dict
        if "timestamp" in kwargs:
            metadata["timestamp"] = kwargs.pop("timestamp")
        if "sub_agent_id" in kwargs:
            metadata["sub_agent_id"] = kwargs.pop("sub_agent_id")
        if "capability_id" in kwargs:
            metadata["capability_id"] = kwargs.pop("capability_id")
        if "capability_name" in kwargs:
            metadata["capability_name"] = kwargs.pop("capability_name")
        if "context_resources" in kwargs:
            metadata["context_resources"] = kwargs.pop("context_resources")

        # Merge capability context
        if cap_context:
            metadata = {
                **metadata,
                "visibility": "internal",
                "capability_id": cap_context.get("capability_id"),
                "capability_name": cap_context.get("capability_name"),
            }

        return metadata

    async def _preprocess_messages(
        self, raw_messages: list[BaseMessage], deduplicate: bool = True
    ) -> list[BaseMessage]:
        """Preprocess messages: filter, deduplicate, and validate.

        Steps:
        1. Filter out SystemMessages (context/instructions, not conversation)
        2. Deduplicate: check which messages already exist in database
        3. Return ready-to-save messages

        Args:
            raw_messages: Raw LangChain messages to process
            deduplicate: If True, filter out duplicate messages

        Returns:
            Filtered and deduplicated messages ready for saving
        """
        if not raw_messages:
            return []

        # Step 1: Filter out SystemMessages
        messages_to_process = [msg for msg in raw_messages if not isinstance(msg, SystemMessage)]

        if len(messages_to_process) < len(raw_messages):
            skipped = len(raw_messages) - len(messages_to_process)
            self.logger.debug(f"Skipped {skipped} SystemMessage(s) - not persisting to database")

        if not messages_to_process:
            self.logger.debug("No messages to save after filtering SystemMessages")
            return []

        # Step 2: Deduplicate
        if not deduplicate:
            return messages_to_process

        existing_message_ids = set()
        message_ids_to_check = [msg.id for msg in messages_to_process if msg.id]

        if message_ids_to_check:
            existing_messages = await self.message_repo.get_messages_by_ids(message_ids_to_check)
            existing_message_ids = {msg.message_id for msg in existing_messages}

        # Filter out existing messages
        messages_to_save = [msg for msg in messages_to_process if msg.id not in existing_message_ids]

        if len(messages_to_save) < len(messages_to_process):
            self.logger.debug(f"Skipped {len(messages_to_process) - len(messages_to_save)} duplicate messages")

        if not messages_to_save:
            self.logger.debug("No new messages to add after deduplication")

        return messages_to_save

    async def _load_recent_messages(self, limit: int = 50) -> list[ChatMessage]:
        """Load recent messages from database.

        Args:
            limit: Maximum number of messages to load (default: 50)

        Returns:
            List of recent ChatMessage objects in chronological order
        """
        # Check thread exists
        thread = await self.db.get(ChatThread, self.thread_id)
        if not thread:
            self.logger.warning(f"Thread {self.thread_id} not found")
            return []

        # Agent-scoped loading for sub-agents
        db_messages = await self.message_repo.get_messages_by_agent(
            thread_id=self.thread_id, agent_id=self.agent_id, limit=limit
        )
        # Reverse to ASC order
        db_messages.reverse()
        return db_messages

    async def _is_tool_chain_resolved(self, anchor: ChatMessage) -> bool:
        """Check whether an anchor AI tool-call chain is fully complete."""
        from apps.tenant_app_service.chat.domain import extract_tool_call_ids, is_tool_chain_resolved
        from apps.tenant_app_service.hitl.history import is_hitl_proposal_blocking
        from apps.tenant_app_service.hitl.utils import get_hitl_proposal_id, is_hitl_skipped_sibling_message

        tool_call_ids = extract_tool_call_ids(anchor.tool_calls)
        if not tool_call_ids or not anchor.session_id:
            return False

        last_tool_msg_id: int | None = None
        resolved_tool_call_ids: set[str] = set()
        terminal_hitl_only = True
        for tool_call_id in tool_call_ids:
            tool_msg = await self.message_repo.get_tool_message_by_call_id(self.thread_id, tool_call_id)
            if tool_msg is None:
                return False

            proposal_id = get_hitl_proposal_id(tool_msg)
            if proposal_id:
                if await is_hitl_proposal_blocking(
                    proposal_id,
                    tenant_id=self.tenant_id,
                    db=self.db,
                ):
                    return False
                resolved_tool_call_ids.add(tool_call_id)
                terminal_hitl_only = True
                continue

            if is_hitl_skipped_sibling_message(tool_msg):
                return False

            terminal_hitl_only = False
            resolved_tool_call_ids.add(tool_call_id)
            if last_tool_msg_id is None or tool_msg.id > last_tool_msg_id:
                last_tool_msg_id = tool_msg.id

        if last_tool_msg_id is None:
            if resolved_tool_call_ids.issuperset(tool_call_ids) and terminal_hitl_only:
                return True
            return False

        has_final_ai = await self.message_repo.has_ai_message_after_db_id_in_session(
            self.thread_id,
            self.agent_id,
            last_tool_msg_id,
            anchor.session_id,
        )
        if terminal_hitl_only and resolved_tool_call_ids.issuperset(tool_call_ids):
            return True
        return is_tool_chain_resolved(tool_call_ids, resolved_tool_call_ids, has_final_ai)

    async def _ensure_hitl_context(self, db_messages: list[ChatMessage]) -> list[ChatMessage]:
        """Guarantee in-flight tool/HITL chains are included in the loaded window.

        When a message_limit truncates the unsummarized window, the most recent
        AIMessage with tool_calls (and any ToolMessages that follow it) may be
        excluded, breaking HITL approval flows.  This method detects that case
        and injects the missing tail block.

        Completed chains (all tool responses present and a final AI reply after
        them) are left summarized — no raw tail re-injection.

        Args:
            db_messages: Unsummarized messages already loaded, in ASC chronological order.

        Returns:
            Same list, potentially extended at the front with the HITL tail block.
        """
        last_ai_msg = await self.message_repo.get_last_ai_message_with_tool_calls(self.thread_id, self.agent_id)
        if not last_ai_msg:
            return db_messages

        if await self._is_tool_chain_resolved(last_ai_msg):
            self.logger.debug(
                f"HITL guarantee: skipping resolved tool chain (anchor db_id={last_ai_msg.id}) "
                f"for thread {self.thread_id}"
            )
            return db_messages

        loaded_ids = {msg.id for msg in db_messages}
        if last_ai_msg.id in loaded_ids:
            return db_messages  # Already included, nothing to do

        # The anchor AI message was cut off by the limit (or was summarized).
        # Load it and everything after it so the full tool_call chain is present.
        tail_messages = await self.message_repo.get_messages_from_db_id(
            thread_id=self.thread_id,
            agent_id=self.agent_id,
            from_db_id=last_ai_msg.id,
        )
        if not tail_messages:
            return db_messages

        tail_id_set = {msg.id for msg in tail_messages}
        merged = tail_messages + [msg for msg in db_messages if msg.id not in tail_id_set]
        merged.sort(key=lambda m: (m.created_at, m.id))
        self.logger.info(
            f"HITL guarantee: injected {len(tail_messages)} messages "
            f"(anchor AI tool_call db_id={last_ai_msg.id}) for thread {self.thread_id}"
        )
        return merged

    async def load_messages_with_summary(
        self,
        message_limit: int | None = None,
        thread_summary_limit: int = 1,
        session_summary_limit: int = 2,
    ) -> list[BaseMessage]:
        """Load messages with thread summaries and session summaries.

        Strategy:
        1. Load N most recent thread summaries (compressed long-term history).
        2. Load unsummarized session summaries — sessions not yet rolled into a
           thread summary (``included_in_thread_summary=False``).  ``session_summary_limit``
           caps the number of sessions shown (most recent N).
        3. Load unsummarized messages (``is_summarized=False``), capped at
              ``message_limit`` (``None`` = no cap, ``0`` = zero messages).
        4. HITL guarantee: ensure the last AIMessage with tool_calls and all
           subsequent messages are always present so HITL approval can continue.

        Args:
            message_limit: Max unsummarized messages to load. ``None`` means no cap;
                ``0`` means load zero unsummarized messages.
            thread_summary_limit: Number of most-recent thread summaries to include.
            session_summary_limit: Max unsummarized session summaries to include.

        Returns:
            List of LangChain messages:
            [thread summaries] + [session summaries] + [unsummarized messages]
        """
        # Check thread exists
        thread = await self.db.get(ChatThread, self.thread_id)
        if not thread:
            self.logger.warning(f"Thread {self.thread_id} not found")
            return []

        messages = []
        thread_summary_count = 0
        session_summary_count = 0

        # Step 1: Load thread summaries from ThreadSummary table
        if thread_summary_limit > 0:
            from apps.tenant_app_service.chat.thread_summary_repository import ThreadSummaryRepository

            thread_summary_repo = ThreadSummaryRepository(self.db)
            thread_summaries = await thread_summary_repo.get_recent_summaries(
                self.thread_id, limit=thread_summary_limit
            )

            if thread_summaries:
                # Combine all thread summaries into single SystemMessage
                summary_parts = []
                for i, ts in enumerate(reversed(thread_summaries), 1):
                    summary_parts.append(
                        f"## Thread Summary v{ts.version}\n"
                        f"(Sessions: {ts.session_range}, Messages: {ts.message_range})\n\n"
                        f"{ts.summary_content}"
                    )

                combined_summary = "\n\n---\n\n".join(summary_parts)
                messages.append(
                    SystemMessage(
                        content=f"# Thread History Summaries\n\n{combined_summary}",
                        additional_kwargs={
                            "summary_type": "thread_summary",
                            "summary_count": len(thread_summaries),
                        },
                    )
                )
            thread_summary_count = len(thread_summaries)

        # Step 2: Load unsummarized session summaries
        # (sessions not yet rolled into any thread summary)
        if session_summary_limit > 0:
            from apps.tenant_app_service.chat.session_summary_repository import SessionSummaryRepository

            session_repo = SessionSummaryRepository(self.db)
            # Returns ASC order (oldest first); apply limit to take most recent N
            unsummarized_sessions = await session_repo.get_unsummarized_sessions(self.thread_id)
            if len(unsummarized_sessions) > session_summary_limit:
                unsummarized_sessions = unsummarized_sessions[-session_summary_limit:]

            if unsummarized_sessions:
                session_lines = []
                for i, ss in enumerate(unsummarized_sessions, 1):
                    session_lines.append(f"{i}. {ss.summary_text}")

                session_context = "\n".join(session_lines)
                messages.append(
                    SystemMessage(
                        content=f"# Recent Session Summaries\n\n{session_context}",
                        additional_kwargs={"summary_type": "session_summary"},
                    )
                )
                session_summary_count = len(unsummarized_sessions)

        # Step 3: Load unsummarized messages only
        actual_limit = message_limit
        raw_db_messages = await self.message_repo.get_unsummarized_messages(
            thread_id=self.thread_id,
            agent_id=self.agent_id,
            limit=actual_limit,
        )
        # get_unsummarized_messages returns DESC; reverse to ASC chronological
        raw_db_messages.reverse()

        # Step 4: HITL guarantee — inject last AI tool_call block if cut off
        raw_db_messages = await self._ensure_hitl_context(raw_db_messages)

        lc_messages = [_db_message_to_langchain(msg) for msg in raw_db_messages]
        messages.extend(lc_messages)

        self.logger.info(
            f"Loaded context for thread {self.thread_id}, agent_id: {self.agent_id}: "
            f"{thread_summary_count} thread summaries, "
            f"{session_summary_count} unsummarized session summaries, "
            f"{len(raw_db_messages)} unsummarized messages"
        )
        return messages

    async def add_messages(
        self,
        raw_messages: list[BaseMessage],
        config: RunnableConfig,
        deduplicate: bool = True,
    ) -> None:
        """Add new messages and immediately save to database.

        This method:
        1. Preprocesses messages (filter, deduplicate)
        2. Converts BaseMessage → ChatMessage
        3. Saves to database
        4. Updates internal cache

        Args:
            raw_messages: List of new LangChain messages to add
            config: Runtime configuration
            deduplicate: If True, skip messages with IDs that already exist
        """
        # Preprocess: filter and deduplicate messages
        messages_to_save = await self._preprocess_messages(raw_messages, deduplicate)
        if not messages_to_save:
            return

        # Get thread
        thread = await self.db.get(ChatThread, self.thread_id)
        if not thread:
            self.logger.warning(f"Thread {self.thread_id} not found, cannot add messages")
            return

        # Convert to ChatMessage
        db_messages = []
        cap_context = config.get("configurable", {}).get("capability_call_context", {})
        runtime_context = extract_runtime_context(config)

        for msg in messages_to_save:
            message_id = msg.id
            kwargs = msg.additional_kwargs or {}
            kwargs = _serialize_additional_kwargs(kwargs)

            # Extract timestamp and metadata from message
            msg_timestamp = self._extract_message_timestamp(kwargs)
            metadata = self._extract_message_metadata(kwargs, cap_context)

            if msg.type == "tool" and hasattr(msg, "tool_call_id"):
                kwargs = {**(kwargs or {}), "tool_call_id": msg.tool_call_id}

            tool_calls = None
            if msg.type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = _serialize_additional_kwargs(msg.tool_calls)

            if msg.type == "ai":
                content = normalize_message_content(msg.content)
            else:
                content = msg.content if isinstance(msg.content, str) else str(msg.content or "")

            db_msg = ChatMessage(
                message_id=message_id,
                thread_id=self.thread_id,
                session_id=runtime_context.session_id,
                agent_id=runtime_context.agent_id,
                type=msg.type,
                content=content,
                timestamp=msg_timestamp,
                is_summarized=False,
                tool_calls=tool_calls,
                additional_kwargs=kwargs,
                message_metadata=metadata,
            )
            db_messages.append(db_msg)

        # Batch save
        await self.message_repo.save_messages_batch(db_messages)

        # Update thread message count
        thread.message_count = thread.message_count + len(db_messages)
        await self.db.commit()

        self.logger.info(
            f"Added {len(db_messages)} messages to thread {self.thread_id} (total: {thread.message_count})"
        )

    async def get_last_message(self) -> ChatMessage | None:
        """Get the last message from database.

        Returns:
            Last ChatMessage or None if no messages
        """
        recent_messages = await self._load_recent_messages(limit=1)
        return recent_messages[-1] if recent_messages else None

    async def save_messages(
        self,
        thread_id: str,
        raw_messages: list[BaseMessage],
        config: RunnableConfig,
        deduplicate: bool = True,
    ) -> None:
        """Save new messages to database (legacy method, delegates to add_messages).

        Deprecated: Use add_messages() instead for new code.
        This method is kept for backward compatibility.

        Args:
            thread_id: Thread ID to save messages to
            messages: List of new LangChain messages to save
            deduplicate: If True, skip messages with IDs that already exist
        """
        # Delegate to add_messages if thread_id matches
        if thread_id != self.thread_id:
            self.logger.warning(
                f"save_messages called with thread_id={thread_id} but manager has thread_id={self.thread_id}"
            )
            return

        await self.add_messages(raw_messages, config, deduplicate)
