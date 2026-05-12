"""Notification domain models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

CHANNEL_IN_APP = "in_app"
CHANNEL_EMAIL = "email"
CHANNEL_SLACK = "slack"
CHANNEL_WECOM = "wecom"
CHANNEL_DINGDING = "dingding"

NotificationChannelType = Literal[
    "in_app",
    "email",
    "slack",
    "wecom",
    "dingding",
]

ALL_NOTIFICATION_CHANNEL_TYPES: tuple[NotificationChannelType, ...] = (
    CHANNEL_IN_APP,
    CHANNEL_EMAIL,
    CHANNEL_SLACK,
    CHANNEL_WECOM,
    CHANNEL_DINGDING,
)


def is_valid_notification_channel(channel: str) -> bool:
    """Return whether the channel is a supported notification type."""
    return channel in ALL_NOTIFICATION_CHANNEL_TYPES


@dataclass
class NotificationEvent:
    """Channel-agnostic notification event."""

    tenant_id: int
    user_id: int
    event_type: str
    title: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
