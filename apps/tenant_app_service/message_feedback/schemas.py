"""DTOs for message feedback."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SubmitFeedbackRequest(BaseModel):
    rating: Literal["positive", "negative"]
    comment: str | None = Field(None, max_length=2000)


class FeedbackResponse(BaseModel):
    message_id: str
    rating: Literal["positive", "negative"]
    comment: str | None = None
    source: Literal["portal", "slack"] = "portal"
    created_at: datetime
    updated_at: datetime


class ThreadFeedbackMapResponse(BaseModel):
    thread_id: str
    feedback: dict[str, FeedbackResponse]


class FeedbackAgentStats(BaseModel):
    agent_id: int
    positive_count: int
    negative_count: int
    total_count: int


class FeedbackStatsResponse(BaseModel):
    positive_count: int
    negative_count: int
    total_count: int
    positive_rate: float
    by_agent: list[FeedbackAgentStats]


class FeedbackListItem(BaseModel):
    id: int
    thread_id: str
    session_id: str | None
    message_id: str
    agent_id: int
    user_id: int
    username: str | None = None
    rating: Literal["positive", "negative"]
    comment: str | None
    source: Literal["portal", "slack"]
    human_message_preview: str | None = None
    ai_message_preview: str | None = None
    created_at: datetime


class FeedbackListResponse(BaseModel):
    items: list[FeedbackListItem]
    next_cursor: int | None = None
    has_more: bool = False
