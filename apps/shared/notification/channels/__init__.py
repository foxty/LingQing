"""Notification channel adapters."""

from apps.shared.notification.channels.dingding import DingDingChannel
from apps.shared.notification.channels.email import EmailChannel
from apps.shared.notification.channels.in_app import InAppChannel
from apps.shared.notification.channels.slack import SlackChannel
from apps.shared.notification.channels.wecom import WeComChannel

__all__ = [
    "DingDingChannel",
    "EmailChannel",
    "InAppChannel",
    "SlackChannel",
    "WeComChannel",
]
