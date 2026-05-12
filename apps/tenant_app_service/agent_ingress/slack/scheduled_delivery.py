"""Deliver scheduled agent_run results back to originating Slack threads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort, SlackWebClient
from apps.tenant_app_service.agent_ingress.slack.domain import format_reply_for_slack, split_long_text
from apps.tenant_app_service.agent_ingress.slack.messages import SLACK_SCHEDULED_FAILURE_MESSAGE
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository

logger = get_logger(__name__)

__all__ = [
    "SLACK_SCHEDULED_FAILURE_MESSAGE",
    "deliver_scheduled_agent_run_to_slack",
    "slack_delivery_thread_ts",
]


def slack_delivery_thread_ts(external_thread_key: str) -> str | None:
    return external_thread_key or None


async def deliver_scheduled_agent_run_to_slack(
    *,
    tenant_id: int,
    user_id: int,
    origin_thread_id: str | None,
    response_text: str,
    db_session: AsyncSession,
    client: SlackClientPort | None = None,
) -> bool:
    if not origin_thread_id:
        return False

    repo = SlackRepository(db_session)
    link = await repo.get_thread_link_by_chat_thread_id(tenant_id, origin_thread_id)
    if link is None:
        return False

    from sqlalchemy import select

    from apps.shared.db.models import AgentIngressEndpoint

    result = await db_session.execute(
        select(AgentIngressEndpoint).where(AgentIngressEndpoint.id == link.endpoint_id)
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint or not endpoint.enabled:
        logger.debug(
            "Slack scheduled delivery skip: endpoint missing or disabled tenant=%s user=%s",
            tenant_id,
            user_id,
        )
        return False

    settings = get_settings()
    formatted_text = format_reply_for_slack(
        response_text,
        portal_origin=settings.PORTAL_ORIGIN,
        api_origin=settings.TENANT_APP_API_ORIGIN,
    )
    thread_ts = slack_delivery_thread_ts(link.external_thread_key)
    bot_token = repo.decrypt_bot_token(endpoint)
    slack_client = client or SlackWebClient()

    try:
        for chunk in split_long_text(formatted_text):
            await slack_client.chat_post_message(
                bot_token=bot_token,
                channel=link.external_channel_id,
                text=chunk,
                thread_ts=thread_ts,
            )
        logger.info(
            "Slack scheduled delivery succeeded: tenant=%s user=%s thread=%s channel=%s",
            tenant_id,
            user_id,
            origin_thread_id,
            link.external_channel_id,
        )
        return True
    except Exception:
        logger.exception(
            "Slack scheduled delivery failed: tenant=%s user=%s thread=%s",
            tenant_id,
            user_id,
            origin_thread_id,
        )
        return False
