"""Email notification channel placeholder."""

from typing import Any

from apps.shared.notification.domain import CHANNEL_EMAIL, NotificationChannelType, NotificationEvent
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class EmailChannel:
    """Email channel adapter.

    This adapter is intentionally lightweight for now and can be wired to
    SMTP/provider SDK later without changing dispatcher contracts.
    """

    channel_type: NotificationChannelType = CHANNEL_EMAIL

    async def send(self, event: NotificationEvent, channel_config: dict[str, Any]) -> bool:
        logger.info(
            "Email channel dispatch placeholder: event_type=%s tenant=%s user=%s",
            event.event_type,
            event.tenant_id,
            event.user_id,
        )
        return True
