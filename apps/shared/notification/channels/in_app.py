"""In-app notification channel implementation."""

from typing import Any

from apps.shared.notification.domain import CHANNEL_IN_APP, NotificationChannelType, NotificationEvent
from apps.shared.notification.repository import NotificationRepository


class InAppChannel:
    """Persist notification into inbox table for frontend polling."""

    channel_type: NotificationChannelType = CHANNEL_IN_APP

    def __init__(self, repository: NotificationRepository):
        self.repository = repository

    async def send(self, event: NotificationEvent, channel_config: dict[str, Any]) -> bool:
        await self.repository.create_notification(
            tenant_id=event.tenant_id,
            user_id=event.user_id,
            event_type=event.event_type,
            title=event.title,
            payload=event.payload,
        )
        return True
