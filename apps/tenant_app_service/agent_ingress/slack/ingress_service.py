"""Runtime Slack ingress orchestration (events → identity → chat → reply).

Portal admin config lives in ``admin_service``; HTTP webhooks in ``ingress_router``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.core.exceptions import DomainException
from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.external_identity import BindAction
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.access import is_eligible_slack_identity, user_has_chat_access
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort, SlackWebClient
from apps.tenant_app_service.agent_ingress.slack.domain import (
    SlackMessageEvent,
    ensure_slack_reply_text,
    format_reply_for_slack,
    slack_mapping_thread_ts,
    slack_reply_thread_ts,
    strip_bot_mention,
)
from apps.tenant_app_service.agent_ingress.slack.feedback_delivery import (
    post_slack_reply_with_feedback,
    resolve_feedback_message_id,
)
from apps.tenant_app_service.agent_ingress.slack.identity_service import SlackIdentityService
from apps.tenant_app_service.agent_ingress.slack.messages import (
    SLACK_INTEGRATION_DISABLED_MESSAGE,
    SlackMessageKey,
    slack_chat_error_message,
    slack_identity_user_message,
    slack_user_message,
)
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.auth.token import JwtTokenIssuer
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.service import ChatService

logger = get_logger(__name__)


class SlackIngressService:
    """Orchestrate Slack event → identity → chat → reply."""

    def __init__(
        self,
        db: AsyncSession,
        client: SlackClientPort | None = None,
        identity_service: SlackIdentityService | None = None,
        token_issuer: JwtTokenIssuer | None = None,
    ):
        self.db = db
        self.repo = SlackRepository(db)
        self.client = client or SlackWebClient()
        self.identity_service = identity_service or SlackIdentityService(db, client=client)
        self.token_issuer = token_issuer or JwtTokenIssuer()

    async def notify_disabled(self, event: SlackMessageEvent, endpoint_id: int) -> None:
        endpoint = await self._get_endpoint(endpoint_id)
        if not endpoint:
            return
        bot_token = self.repo.decrypt_bot_token(endpoint)
        await self._post_ephemeral(bot_token, event, SLACK_INTEGRATION_DISABLED_MESSAGE)

    async def handle_message(self, event: SlackMessageEvent, endpoint_id: int) -> None:
        endpoint = await self._get_endpoint(endpoint_id)
        if not endpoint or not endpoint.enabled:
            logger.info("Slack ingress endpoint disabled or missing id=%s", endpoint_id)
            return

        tenant_id = endpoint.tenant_id
        bot_token = self.repo.decrypt_bot_token(endpoint)

        result = await self.identity_service.resolve_slack_user(
            tenant_id=tenant_id,
            slack_user_id=event.user_id,
            endpoint=endpoint,
        )
        if result is None:
            await self._post_ephemeral(
                bot_token, event, slack_user_message(SlackMessageKey.SLACK_VERIFY_FAILED)
            )
            return

        if not is_eligible_slack_identity(result):
            if result.action in {BindAction.DENY, BindAction.PENDING}:
                await self._post_ephemeral(
                    bot_token,
                    event,
                    slack_identity_user_message(action=result.action, reason=result.reason),
                )
            elif result.user_id is None:
                logger.warning(
                    "Slack bind returned %s with no user_id for tenant %s",
                    result.action,
                    tenant_id,
                )
            return

        if not await user_has_chat_access(self.db, tenant_id, result.user_id):
            await self._post_ephemeral(
                bot_token, event, slack_user_message(SlackMessageKey.CHAT_PERMISSION_DENIED)
            )
            return

        resolved = await self._resolve_thread_id(
            tenant_id=tenant_id,
            event=event,
            endpoint=endpoint,
            user_id=result.user_id,
        )
        if resolved is None:
            return
        thread_id, agent_id = resolved

        message_text = (
            strip_bot_mention(event.text, event.bot_user_id)
            if event.source == "app_mention"
            else event.text
        )
        if not message_text.strip():
            await self._post_ephemeral(
                bot_token, event, slack_user_message(SlackMessageKey.EMPTY_MENTION_MESSAGE)
            )
            return

        user_dto, tenant_name = await self._build_user_dto(tenant_id, result.user_id)
        if user_dto is None:
            await self._post_ephemeral(
                bot_token, event, slack_user_message(SlackMessageKey.LINKED_ACCOUNT_NOT_FOUND)
            )
            return

        access_token = self.token_issuer.issue(
            user_id=user_dto.id,
            username=user_dto.username,
            role=user_dto.role,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )

        reply_thread_ts = slack_reply_thread_ts(
            channel_type=event.channel_type,
            thread_ts=event.thread_ts,
            message_ts=event.ts,
        )

        thinking = await self.client.chat_post_message(
            bot_token=bot_token,
            channel=event.channel_id,
            text=slack_user_message(SlackMessageKey.THINKING_PLACEHOLDER),
            thread_ts=reply_thread_ts,
        )
        thinking_ts = thinking.get("ts") if thinking else None

        message_id: str | None = None
        session_id: str | None = None
        try:
            chat_service = ChatService(tenant_id, self.db)
            chat_request = ChatRequest(
                tenant_id=tenant_id,
                agent_id=agent_id,
                message=SimpleMessage(role="human", content=message_text),
                thread_id=thread_id,
            )
            settings = get_settings()
            response = await chat_service.chat(chat_request, current_user=user_dto, access_token=access_token)
            message_id = response.response.message_id
            session_id = response.response.session_id
            reply_text = format_reply_for_slack(
                response.response.content
                if isinstance(response.response.content, str)
                else str(response.response.content),
                portal_origin=settings.PORTAL_ORIGIN,
                api_origin=settings.TENANT_APP_API_ORIGIN,
            )
        except DomainException as exc:
            logger.warning(
                "Slack chat failed for tenant %s user %s: %s",
                tenant_id,
                result.user_id,
                exc.message,
            )
            reply_text = slack_chat_error_message(exc)
        except Exception:
            logger.exception("Slack chat invocation failed for tenant %s user %s", tenant_id, result.user_id)
            reply_text = slack_user_message(SlackMessageKey.CHAT_GENERIC_FAILURE)

        reply_text = ensure_slack_reply_text(reply_text)

        message_repo = MessageRepository(self.db)
        message_id = await resolve_feedback_message_id(
            message_repo,
            message_id=message_id,
            session_id=session_id,
            thread_id=thread_id,
        )
        await post_slack_reply_with_feedback(
            client=self.client,
            bot_token=bot_token,
            channel_id=event.channel_id,
            text=reply_text,
            message_id=message_id,
            thread_ts=reply_thread_ts,
            message_repo=message_repo,
            update_ts=thinking_ts,
        )

    async def _get_endpoint(self, endpoint_id: int) -> AgentIngressEndpoint | None:
        result = await self.db.execute(
            select(AgentIngressEndpoint).where(AgentIngressEndpoint.id == endpoint_id)
        )
        return result.scalar_one_or_none()

    async def _post_ephemeral(self, bot_token: str, event: SlackMessageEvent, text: str) -> None:
        try:
            await self.client.chat_post_message(
                bot_token=bot_token,
                channel=event.channel_id,
                text=text,
                thread_ts=slack_reply_thread_ts(
                    channel_type=event.channel_type,
                    thread_ts=event.thread_ts,
                    message_ts=event.ts,
                ),
            )
        except Exception:
            logger.exception("Failed to post Slack reply to channel %s", event.channel_id)

    async def _resolve_thread_id(
        self,
        *,
        tenant_id: int,
        event: SlackMessageEvent,
        endpoint: AgentIngressEndpoint,
        user_id: int,
    ) -> tuple[str, int] | None:
        mapping_ts = slack_mapping_thread_ts(event)
        if event.source == "thread_reply":
            mapping = await self.repo.get_thread_link(
                tenant_id,
                event.channel_id,
                mapping_ts,
                endpoint_id=endpoint.id,
            )
            if mapping is None:
                return None
            return await self._align_chat_thread_with_endpoint(
                tenant_id=tenant_id,
                event=event,
                endpoint=endpoint,
                user_id=user_id,
                mapping=mapping,
                mapping_ts=mapping_ts,
            )

        return await self._get_or_create_thread(
            tenant_id=tenant_id,
            event=event,
            endpoint=endpoint,
            user_id=user_id,
            mapping_ts=mapping_ts,
        )

    async def _get_or_create_thread(
        self,
        *,
        tenant_id: int,
        event: SlackMessageEvent,
        endpoint: AgentIngressEndpoint,
        user_id: int,
        mapping_ts: str,
    ) -> tuple[str, int]:
        mapping = await self.repo.get_thread_link(
            tenant_id,
            event.channel_id,
            mapping_ts,
            endpoint_id=endpoint.id,
        )
        if mapping:
            return await self._align_chat_thread_with_endpoint(
                tenant_id=tenant_id,
                event=event,
                endpoint=endpoint,
                user_id=user_id,
                mapping=mapping,
                mapping_ts=mapping_ts,
            )

        agent_id = endpoint.agent_id
        thread = await self._create_slack_thread(
            tenant_id=tenant_id,
            event=event,
            user_id=user_id,
            agent_id=agent_id,
            mapping_ts=mapping_ts,
        )
        await self.repo.create_thread_link(
            tenant_id=tenant_id,
            endpoint_id=endpoint.id,
            agent_id=agent_id,
            external_user_id=event.user_id,
            external_channel_id=event.channel_id,
            external_thread_key=mapping_ts,
            chat_thread_id=thread.id,
        )
        return thread.id, agent_id

    async def _align_chat_thread_with_endpoint(
        self,
        *,
        tenant_id: int,
        event: SlackMessageEvent,
        endpoint: AgentIngressEndpoint,
        user_id: int,
        mapping,
        mapping_ts: str,
    ) -> tuple[str, int]:
        """Reuse the ingress link, rebinding when the chat thread is missing or agent changed."""
        agent_id = endpoint.agent_id
        chat_service = ChatService(tenant_id, self.db)
        thread = await chat_service.get_thread(mapping.chat_thread_id)
        if thread is None or thread.agent_id != agent_id:
            new_thread = await self._create_slack_thread(
                tenant_id=tenant_id,
                event=event,
                user_id=user_id,
                agent_id=agent_id,
                mapping_ts=mapping_ts,
            )
            await self.repo.update_thread_link(
                mapping,
                chat_thread_id=new_thread.id,
                agent_id=agent_id,
            )
            return new_thread.id, agent_id
        return mapping.chat_thread_id, agent_id

    async def _create_slack_thread(
        self,
        *,
        tenant_id: int,
        event: SlackMessageEvent,
        user_id: int,
        agent_id: int,
        mapping_ts: str,
    ):
        if event.channel_type == "im":
            title = f"Slack DM with {event.user_id}"
        else:
            title = f"Slack channel thread {mapping_ts or event.channel_id}"
        chat_service = ChatService(tenant_id, self.db)
        return await chat_service.create_thread(
            user_id=user_id,
            agent_id=agent_id,
            title=title,
            first_message=event.text,
        )

    async def _build_user_dto(self, tenant_id: int, user_id: int) -> tuple[UserDTO | None, str]:
        from apps.tenant_app_service.tenant.repository import TenantRepository

        user_repo = UserRepository(self.db)
        tenant_repo = TenantRepository(self.db)
        tenant = await tenant_repo.get_by_id(tenant_id)
        tenant_name = tenant.name if tenant else ""
        membership = await user_repo.get_user_membership(tenant_id, user_id)
        if not membership:
            return None, tenant_name
        user, _membership = membership
        return (
            UserDTO(
                id=user.id,
                username=user.username,
                email=user.email or "",
                role=user.role,
                tenant_id=tenant_id,
                tenant_name=tenant_name,
            ),
            tenant_name,
        )

