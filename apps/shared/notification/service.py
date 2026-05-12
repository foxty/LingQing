"""Notification service facade."""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.notification.dispatcher import NotificationDispatcher
from apps.shared.notification.domain import NotificationChannelType, NotificationEvent
from apps.shared.notification.repository import NotificationPreferenceRepository, NotificationRepository


class NotificationService:
    """High-level API for notification use cases."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NotificationRepository(session)
        self.pref_repo = NotificationPreferenceRepository(session)
        self.dispatcher = NotificationDispatcher(session)

    async def dispatch_event(
        self,
        event: NotificationEvent,
        *,
        channel_override: list[NotificationChannelType] | None = None,
    ) -> None:
        await self.dispatcher.dispatch(event, channel_override=channel_override)
