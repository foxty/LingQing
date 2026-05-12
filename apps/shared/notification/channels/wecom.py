"""WeCom notification channel placeholder."""

from typing import Any

from apps.shared.notification.domain import CHANNEL_WECOM, NotificationChannelType, NotificationEvent
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class WeComChannel:
    """WeCom bot webhook adapter."""

    channel_type: NotificationChannelType = CHANNEL_WECOM

    async def send(self, event: NotificationEvent, channel_config: dict[str, Any]) -> bool:
        logger.info(
            "WeCom channel dispatch placeholder: event_type=%s tenant=%s user=%s",
            event.event_type,
            event.tenant_id,
            event.user_id,
        )
        return True
