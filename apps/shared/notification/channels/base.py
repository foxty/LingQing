"""Notification channel protocol."""

from typing import Any, Protocol

from apps.shared.notification.domain import NotificationChannelType, NotificationEvent


class NotificationChannel(Protocol):
    """Contract for notification delivery channels."""

    channel_type: NotificationChannelType

    async def send(self, event: NotificationEvent, channel_config: dict[str, Any]) -> bool:
        """Deliver event to the target channel."""
