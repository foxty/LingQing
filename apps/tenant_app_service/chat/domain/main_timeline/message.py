"""Main timeline row entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ThreadMainMessageDomain:
    id: int
    message_id: str
    thread_id: str
    type: str
    content: str
    timestamp: datetime
    agent_id: int | None = None
    trigger_message_id: str | None = None
    agent_run_id: str | None = None
    invoke_index: int | None = None
    session_id: str | None = None
    additional_kwargs: dict | None = None
    message_metadata: dict | None = None
    created_at: datetime | None = None


MainTimelineMessage = ThreadMainMessageDomain
