"""Domain models for message feedback."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from apps.shared.core.exceptions import ValidationError

FEEDBACK_COMMENT_MAX_LENGTH: Final = 1000

FEEDBACK_RATING_POSITIVE: Final = "positive"
FEEDBACK_RATING_NEGATIVE: Final = "negative"

FEEDBACK_SOURCE_PORTAL: Final = "portal"
FEEDBACK_SOURCE_SLACK: Final = "slack"

FeedbackRating = Literal["positive", "negative"]
FeedbackSource = Literal["portal", "slack"]


def normalize_feedback_comment(text: str | None) -> str | None:
    """Strip and enforce max length for optional user feedback comments."""
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) > FEEDBACK_COMMENT_MAX_LENGTH:
        raise ValidationError(f"Comment must be at most {FEEDBACK_COMMENT_MAX_LENGTH} characters")
    return stripped


def normalize_message_content(text: str | None) -> str | None:
    """Return stripped message text, or None when empty."""
    if not text:
        return None
    stripped = text.strip()
    return stripped if stripped else None


def truncate_preview(text: str | None, *, max_len: int = 200) -> str | None:
    """Return trimmed text truncated with ellipsis when over max_len."""
    stripped = normalize_message_content(text)
    if stripped is None:
        return None
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."


@dataclass(frozen=True)
class FeedbackTargetMessage:
    """AI message row used to anchor feedback (main timeline or run store)."""

    id: int
    message_id: str
    thread_id: str
    session_id: str | None
    agent_id: int | None
    content: str | None = None
    trigger_message_id: str | None = None


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
