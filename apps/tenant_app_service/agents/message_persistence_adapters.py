"""Adapters: run/main persistence rows ↔ ChatMessage shim ↔ LangChain messages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from apps.shared.db.models import AgentRunMessage, ChatMessage
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class _MainTimelineRow(Protocol):
    message_id: str
    content: str
    type: str
    timestamp: datetime
    additional_kwargs: dict | None


def agent_run_message_to_chat_message(row: AgentRunMessage) -> ChatMessage:
    """Adapt agent_run_messages row to ChatMessage shape for shared helpers."""
    return ChatMessage(
        id=row.id,
        message_id=row.message_id,
        thread_id=row.thread_id,
        type=row.type,
        content=row.content,
        is_summarized=row.is_summarized,
        tool_calls=row.tool_calls,
        additional_kwargs=row.additional_kwargs,
        session_id=row.session_id,
        agent_id=row.agent_id,
        timestamp=row.timestamp,
        message_metadata=row.message_metadata,
        created_at=row.created_at,
    )


def agent_run_messages_to_chat_messages(rows: list[AgentRunMessage]) -> list[ChatMessage]:
    return [agent_run_message_to_chat_message(row) for row in rows]


def chat_message_to_langchain(db_msg: ChatMessage) -> BaseMessage:
    """Convert ChatMessage (or run shim) to LangChain message."""
    message_id = db_msg.message_id if db_msg.message_id else str(db_msg.id)
    content = db_msg.content
    additional_kwargs = db_msg.additional_kwargs or {}
    if db_msg.message_metadata:
        additional_kwargs = {**additional_kwargs}
        ts = db_msg.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        else:
            ts = ts.astimezone(UTC)
        additional_kwargs["timestamp"] = ts.isoformat()

    if db_msg.type == "human":
        return HumanMessage(id=message_id, content=content, additional_kwargs=additional_kwargs)
    if db_msg.type == "ai":
        ai_kwargs = {"id": message_id, "content": content, "additional_kwargs": additional_kwargs}
        if db_msg.tool_calls:
            ai_kwargs["tool_calls"] = db_msg.tool_calls
        return AIMessage(**ai_kwargs)
    if db_msg.type == "system":
        return SystemMessage(id=message_id, content=content, additional_kwargs=additional_kwargs)
    if db_msg.type == "tool":
        tool_call_id = db_msg.additional_kwargs.get("tool_call_id") if db_msg.additional_kwargs else None
        if not tool_call_id:
            logger.warning(
                "ToolMessage %s missing tool_call_id in additional_kwargs. "
                "This should not happen in normal operation.",
                message_id,
            )
            tool_call_id = message_id
        return ToolMessage(
            id=message_id,
            content=content,
            tool_call_id=tool_call_id,
            additional_kwargs=additional_kwargs,
        )
    logger.warning("Unknown message type: %s, defaulting to HumanMessage", db_msg.type)
    return HumanMessage(id=message_id, content=content, additional_kwargs=additional_kwargs)


def thread_main_message_domain_to_langchain(row: _MainTimelineRow) -> BaseMessage:
    """Convert main timeline domain row to LangChain (human or promoted AI)."""
    additional_kwargs = row.additional_kwargs or {}
    ts = row.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    else:
        ts = ts.astimezone(UTC)
    additional_kwargs = {**additional_kwargs, "timestamp": ts.isoformat()}
    if row.type == "human":
        return HumanMessage(id=row.message_id, content=row.content, additional_kwargs=additional_kwargs)
    return AIMessage(id=row.message_id, content=row.content, additional_kwargs=additional_kwargs)


def agent_run_message_to_langchain(row: AgentRunMessage) -> BaseMessage:
    return chat_message_to_langchain(agent_run_message_to_chat_message(row))
