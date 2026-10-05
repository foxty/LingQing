"""Slack notification channel."""

from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from apps.shared.db.models import ExternalIdentity
from apps.shared.db.session import app_db_session
from apps.shared.notification.domain import CHANNEL_SLACK, NotificationChannelType, NotificationEvent
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository

logger = get_logger(__name__)


class SlackChannel:
    """Slack channel adapter — posts notifications to a user's DM channel."""

    channel_type: NotificationChannelType = CHANNEL_SLACK

    async def send(self, event: NotificationEvent, channel_config: dict[str, Any]) -> bool:
        try:
            async with app_db_session() as session:
                from sqlalchemy import select

                repo = SlackRepository(session)
                endpoint = await repo.get_endpoint(event.tenant_id)
                if not endpoint or not endpoint.enabled:
                    logger.debug(
                        "Slack channel skip: no enabled endpoint for tenant %s",
                        event.tenant_id,
                    )
                    return False

                bot_token = repo.decrypt_bot_token(endpoint)
                team_id = repo.slack_team_id(endpoint)
                source_repo = SlackIdentitySourceRepository(session)
                identity_source = await source_repo.ensure_slack_workspace_source(
                    tenant_id=event.tenant_id,
                    team_id=team_id,
                )

                binding_result = await session.execute(
                    select(ExternalIdentity).where(
                        ExternalIdentity.tenant_id == event.tenant_id,
                        ExternalIdentity.identity_source_id == identity_source.id,
                        ExternalIdentity.user_id == event.user_id,
                        ExternalIdentity.status == "active",
                    )
                )
                binding = binding_result.scalar_one_or_none()
                if not binding:
                    logger.debug(
                        "Slack channel skip: no active binding for tenant %s user %s",
                        event.tenant_id,
                        event.user_id,
                    )
                    return False

                slack_user_id = binding.external_subject
                client = AsyncWebClient(token=bot_token)
                try:
                    open_resp = await client.conversations_open(users=slack_user_id)
                    channel_id = open_resp["channel"]["id"]
                    await client.chat_postMessage(
                        channel=channel_id,
                        text=self._format_message(event),
                    )
                    return True
                except SlackApiError as exc:
                    logger.warning(
                        "Slack notification delivery failed tenant=%s user=%s error=%s",
                        event.tenant_id,
                        event.user_id,
                        exc.response.get("error") if exc.response else str(exc),
                    )
                    return False
        except Exception:
            logger.exception(
                "Slack channel unexpected error tenant=%s user=%s",
                event.tenant_id,
                event.user_id,
            )
            return False

    def _format_message(self, event: NotificationEvent) -> str:
        title = event.title or "Notification"
        body = event.payload.get("message") if event.payload else None
        if body:
            return f"*{title}*\n{body}"
        return title
