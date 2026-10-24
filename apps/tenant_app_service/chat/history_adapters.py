"""Adapters: main timeline + run rows → API Message DTOs for conversation history."""

from __future__ import annotations

from apps.shared.db.models import AgentRunMessage
from apps.tenant_app_service.chat.agent_run_domain import ThreadMainMessageDomain
from apps.tenant_app_service.chat.schemas import Message


def main_timeline_rows_to_api_messages(
    rows: list[ThreadMainMessageDomain],
    *,
    thread_id: str,
    default_agent_id: int,
) -> list[Message]:
    """Map main timeline domain rows to API messages (human + promoted AI only)."""
    return [
        main_timeline_row_to_api_message(row, thread_id=thread_id, default_agent_id=default_agent_id)
        for row in rows
        if row.type in ("human", "ai")
    ]


def main_timeline_row_to_api_message(
    row: ThreadMainMessageDomain,
    *,
    thread_id: str,
    default_agent_id: int,
) -> Message:
    meta = dict(row.message_metadata or {})
    if row.trigger_message_id:
        meta["trigger_message_id"] = row.trigger_message_id
    if row.invoke_index is not None:
        meta["invoke_index"] = row.invoke_index
    if row.agent_run_id:
        meta["agent_run_id"] = row.agent_run_id
    return Message(
        message_id=row.message_id,
        role=row.type,
        content=row.content,
        agent_id=row.agent_id or default_agent_id,
        thread_id=thread_id,
        timestamp=row.timestamp.isoformat() if row.timestamp else None,
        session_id=row.session_id,
        message_metadata=meta or None,
    )


def agent_run_row_to_api_message(
    row: AgentRunMessage,
    *,
    thread_id: str,
    default_agent_id: int,
) -> Message:
    kwargs = row.additional_kwargs or {}
    tool_call_id = kwargs.get("tool_call_id") if row.type == "tool" else None
    return Message(
        message_id=row.message_id or str(row.id),
        role=row.type,
        content=row.content,
        agent_id=row.agent_id or default_agent_id,
        thread_id=thread_id,
        timestamp=row.timestamp.isoformat() if row.timestamp else None,
        tool_calls=row.tool_calls if row.type == "ai" else None,
        tool_call_id=tool_call_id,
        session_id=row.session_id,
        message_metadata=row.message_metadata,
        additional_kwargs=row.additional_kwargs,
    )
