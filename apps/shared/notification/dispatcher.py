"""Notification channel dispatch orchestration."""

from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.notification.channels import (
    DingDingChannel,
    EmailChannel,
    InAppChannel,
    SlackChannel,
    WeComChannel,
)
from apps.shared.notification.channels.base import NotificationChannel
from apps.shared.notification.domain import (
    CHANNEL_DINGDING,
    CHANNEL_EMAIL,
    CHANNEL_IN_APP,
    CHANNEL_SLACK,
    CHANNEL_WECOM,
    NotificationChannelType,
    NotificationEvent,
    is_valid_notification_channel,
)
from apps.shared.notification.repository import NotificationPreferenceRepository, NotificationRepository
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class NotificationDispatcher:
    """Resolve target channels and fan out notification delivery."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.notification_repo = NotificationRepository(session)
        self.preference_repo = NotificationPreferenceRepository(session)
        self.channels: dict[NotificationChannelType, NotificationChannel] = {
            CHANNEL_IN_APP: InAppChannel(self.notification_repo),
            CHANNEL_EMAIL: EmailChannel(),
            CHANNEL_SLACK: SlackChannel(),
            CHANNEL_WECOM: WeComChannel(),
            CHANNEL_DINGDING: DingDingChannel(),
        }

    async def dispatch(
        self,
        event: NotificationEvent,
        *,
        channel_override: list[NotificationChannelType] | None = None,
    ) -> None:
        targets = await self._resolve_channels(event, channel_override=channel_override)

        for channel_name, channel_config in targets:
            channel = self.channels.get(channel_name)
            if not channel:
                logger.warning("Unknown notification channel: %s", channel_name)
                continue
            try:
                await channel.send(event, channel_config)
            except Exception:
                logger.exception("Notification dispatch failed on channel=%s event=%s", channel_name, event.event_id)

    async def _resolve_channels(
        self,
        event: NotificationEvent,
        *,
        channel_override: list[NotificationChannelType] | None = None,
    ) -> list[tuple[NotificationChannelType, dict[str, Any]]]:
        if channel_override:
            return [(channel, {}) for channel in channel_override]

        prefs = await self.preference_repo.get_user_preferences(
            tenant_id=event.tenant_id,
            user_id=event.user_id,
        )
        event_channels: list[NotificationChannelType] = []
        wildcard_channels: list[NotificationChannelType] = []
        for pref in prefs:
            if pref.event_type == event.event_type:
                event_channels.extend(
                    cast(NotificationChannelType, channel)
                    for channel in pref.channels
                    if is_valid_notification_channel(channel)
                )
            elif pref.event_type == "*":
                wildcard_channels.extend(
                    cast(NotificationChannelType, channel)
                    for channel in pref.channels
                    if is_valid_notification_channel(channel)
                )

        selected = event_channels or wildcard_channels or [CHANNEL_IN_APP]
        selected_unique = list(dict.fromkeys(selected))

        configs = await self.preference_repo.get_tenant_channel_configs(tenant_id=event.tenant_id)
        enabled_configs: dict[NotificationChannelType, dict[str, Any]] = {
            cast(NotificationChannelType, row.channel_type): row.config
            for row in configs
            if row.is_enabled and is_valid_notification_channel(row.channel_type)
        }

        resolved: list[tuple[NotificationChannelType, dict[str, Any]]] = []
        for channel in selected_unique:
            if channel == CHANNEL_IN_APP:
                resolved.append((channel, {}))
                continue
            config = enabled_configs.get(channel)
            if config is None:
                logger.warning("Skip channel without enabled tenant config: %s", channel)
                continue
            resolved.append((channel, config))

        if not resolved:
            resolved.append((CHANNEL_IN_APP, {}))
        return resolved
