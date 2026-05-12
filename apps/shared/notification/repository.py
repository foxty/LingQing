"""Repositories for notification persistence and preferences."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import (
    Notification,
    NotificationChannelConfig,
    UserNotificationPreference,
)
from apps.shared.notification.domain import NotificationChannelType, is_valid_notification_channel


class NotificationRepository:
    """Data access for notification inbox entries."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_notification(
        self,
        *,
        tenant_id: int,
        user_id: int,
        event_type: str,
        title: str,
        payload: dict,
    ) -> Notification:
        notification = Notification(
            id=str(uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            title=title,
            payload=payload,
            is_read=False,
        )
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def list_notifications(
        self,
        *,
        tenant_id: int,
        user_id: int,
        is_read: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if is_read is not None:
            stmt = stmt.where(Notification.is_read == is_read)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_read(self, *, notification_id: str, tenant_id: int, user_id: int) -> bool:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.is_read = True
        await self.session.flush()
        return True

    async def mark_all_as_read(self, *, tenant_id: int, user_id: int) -> int:
        stmt = select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            row.is_read = True
        await self.session.flush()
        return len(rows)


class NotificationPreferenceRepository:
    """Data access for user preferences and tenant channel configs."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_preferences(self, *, tenant_id: int, user_id: int) -> list[UserNotificationPreference]:
        stmt = (
            select(UserNotificationPreference)
            .where(
                UserNotificationPreference.tenant_id == tenant_id,
                UserNotificationPreference.user_id == user_id,
            )
            .order_by(UserNotificationPreference.event_type.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_user_preference(
        self,
        *,
        tenant_id: int,
        user_id: int,
        event_type: str,
        channels: list[NotificationChannelType],
    ) -> UserNotificationPreference:
        cleaned_channels = [channel for channel in channels if is_valid_notification_channel(channel)]
        stmt = select(UserNotificationPreference).where(
            UserNotificationPreference.tenant_id == tenant_id,
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.event_type == event_type,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            row.channels = cleaned_channels
            row.updated_at = datetime.now(UTC)
            await self.session.flush()
            await self.session.refresh(row)
            return row

        row = UserNotificationPreference(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            channels=cleaned_channels,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_tenant_channel_configs(
        self,
        *,
        tenant_id: int,
    ) -> list[NotificationChannelConfig]:
        stmt = select(NotificationChannelConfig).where(NotificationChannelConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
