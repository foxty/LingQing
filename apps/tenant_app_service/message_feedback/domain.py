"""Domain models for message feedback."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

FEEDBACK_RATING_POSITIVE: Final = "positive"
FEEDBACK_RATING_NEGATIVE: Final = "negative"

FEEDBACK_SOURCE_PORTAL: Final = "portal"
FEEDBACK_SOURCE_SLACK: Final = "slack"

FeedbackRating = Literal["positive", "negative"]
FeedbackSource = Literal["portal", "slack"]


def truncate_preview(text: str | None, *, max_len: int = 200) -> str | None:
    """Return trimmed text truncated with ellipsis when over max_len."""
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."


@dataclass
class MessageFeedbackDomain:
    """Domain representation of user feedback on an AI message."""

    id: int
    tenant_id: int
    thread_id: str
    session_id: str | None
    message_id: str
    agent_id: int
    user_id: int
    rating: FeedbackRating
    comment: str | None
    source: FeedbackSource
    external_ref: dict | None
    created_at: datetime
    updated_at: datetime
