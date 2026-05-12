"""Notification module exports."""

from apps.shared.notification.domain import (
    ALL_NOTIFICATION_CHANNEL_TYPES,
    CHANNEL_DINGDING,
    CHANNEL_EMAIL,
    CHANNEL_IN_APP,
    CHANNEL_SLACK,
    CHANNEL_WECOM,
    NotificationChannelType,
    NotificationEvent,
)
from apps.shared.notification.service import NotificationService

__all__ = [
    "ALL_NOTIFICATION_CHANNEL_TYPES",
    "CHANNEL_DINGDING",
    "CHANNEL_EMAIL",
    "CHANNEL_IN_APP",
    "CHANNEL_SLACK",
    "CHANNEL_WECOM",
    "NotificationChannelType",
    "NotificationEvent",
    "NotificationService",
]
