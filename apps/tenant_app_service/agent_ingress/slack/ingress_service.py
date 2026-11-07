"""Runtime Slack ingress orchestration (events → identity → turn flow → reply).

Portal admin config lives in ``admin_service``; HTTP webhooks in ``ingress_router``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.core.exceptions import ThreadBusyError
from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.external_identity import BindAction
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.access import is_eligible_slack_identity, user_has_chat_access
from apps.tenant_app_service.agent_ingress.slack.chat_turn_runner import run_slack_chat_turn
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort, SlackWebClient
from apps.tenant_app_service.agent_ingress.slack.domain import (
    SlackEventType,
    SlackIngressAdmissionOutcome,
    SlackMessageEvent,
    channel_chat_blocks_event,
    decide_slack_ingress_admission,
    ensure_slack_reply_text,
    parse_slack_ingress_event,
    slack_event_team_mismatch,
    slack_mapping_thread_ts,
    slack_reply_thread_ts,
    strip_bot_mention,
)
from apps.tenant_app_service.agent_ingress.slack.feedback_delivery import (
    post_slack_reply_with_feedback,
    resolve_feedback_message_id,
)
from apps.tenant_app_service.agent_ingress.slack.identity_service import SlackIdentityService
from apps.tenant_app_service.agent_ingress.slack.ingress_results import (
    SlackEventsIngressResult,
    SlackInteractivityIngressResult,
)
from apps.tenant_app_service.agent_ingress.slack.interactivity_service import (
    SlackInteractivityService,
    parse_interactivity_payload,
)
from apps.tenant_app_service.agent_ingress.slack.messages import (
    SLACK_CHANNEL_CHAT_DISABLED_MESSAGE,
    SLACK_INTEGRATION_DISABLED_MESSAGE,
    SlackMessageKey,
    slack_chat_error_message,
    slack_identity_user_message,
    slack_user_message,
)
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.agent_ingress.slack.run_control_blocks import build_thinking_placeholder_blocks
from apps.tenant_app_service.agent_ingress.slack.webhook_auth import (
    SlackWebhookAuthFailure,
    authenticate_slack_webhook,
)
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.auth.token import JwtTokenIssuer
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.streaming import PreparedChatStream
from apps.tenant_app_service.chat.thread_service import ThreadService

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

    async def process_events_webhook(
        self,
        *,
        endpoint_key: str,
        payload: dict[str, Any],
        body_text: str,
        slack_timestamp: str,
        slack_signature: str,
    ) -> SlackEventsIngressResult:
        """Resolve endpoint, verify signature, and handle an Events API POST."""
        auth = await authenticate_slack_webhook(
            self.repo,
            endpoint_key=endpoint_key,
            body_text=body_text,
            slack_timestamp=slack_timestamp,
            slack_signature=slack_signature,
        )
        if isinstance(auth, SlackWebhookAuthFailure):
            return SlackEventsIngressResult.auth_failed(auth)

        return await self.process_events_api_callback(
            endpoint=auth,
            payload=payload,
            endpoint_label=endpoint_key,
        )

    async def process_events_api_callback(
        self,
        *,
        endpoint: AgentIngressEndpoint,
        payload: dict[str, Any],
        endpoint_label: str,
    ) -> SlackEventsIngressResult:
        """Admit an Events API payload, run side effects, return ingress result (no HTTP)."""
        payload_type = payload.get("type") or "unknown"
        inner_event = payload.get("event") or {}
        event_id = payload.get("event_id")

        if payload_type == SlackEventType.URL_VERIFICATION:
            logger.info("Slack url_verification challenge received %s", endpoint_label)
            return SlackEventsIngressResult.url_verification(payload.get("challenge") or "")

        configured_team_id = self.repo.slack_team_id(endpoint)
        already_processed = False
        if endpoint.enabled:
            preview = parse_slack_ingress_event(inner_event, event_id=event_id)
            if preview and not slack_event_team_mismatch(
                configured_team_id=configured_team_id,
                event_team_id=preview.team_id,
            ):
                already_processed = await self.repo.is_message_already_processed(
                    endpoint.tenant_id,
                    message=preview,
                    delivery_event_id=event_id,
                    inner_event_type=inner_event.get("type"),
                )

        admission = decide_slack_ingress_admission(
            endpoint_enabled=endpoint.enabled,
            platform_config=endpoint.platform_config,
            configured_team_id=configured_team_id,
            inner_event=inner_event,
            event_id=event_id,
            already_processed=already_processed,
        )

        message_event = admission.message_event
        outcome = admission.outcome

        if outcome == SlackIngressAdmissionOutcome.INTEGRATION_DISABLED and message_event:
            logger.info(
                "Slack webhook disabled %s event_id=%s user_id=%s",
                endpoint_label,
                message_event.event_id,
                message_event.user_id,
            )
            await self.db.commit()
            await self.notify_disabled(message_event, endpoint.id)
        elif outcome == SlackIngressAdmissionOutcome.IGNORED:
            logger.info(
                "Slack webhook ignored %s event_id=%s reason=%s",
                endpoint_label,
                event_id,
                admission.ignore_reason or "unknown",
            )
        elif outcome == SlackIngressAdmissionOutcome.TEAM_MISMATCH and message_event:
            logger.warning(
                "Slack team_id mismatch: event=%s configured=%s %s",
                message_event.team_id,
                configured_team_id,
                endpoint_label,
            )
        elif outcome == SlackIngressAdmissionOutcome.CHANNEL_CHAT_DISABLED and message_event:
            logger.info(
                "Slack channel chat disabled %s event_id=%s user_id=%s source=%s",
                endpoint_label,
                message_event.event_id,
                message_event.user_id,
                message_event.source,
            )
            await self.db.commit()
            await self.notify_channel_chat_disabled(message_event, endpoint.id)
        elif outcome == SlackIngressAdmissionOutcome.DUPLICATE and message_event:
            logger.info(
                "Slack duplicate event %s for tenant %s, acking",
                message_event.event_id,
                endpoint.tenant_id,
            )
        elif outcome == SlackIngressAdmissionOutcome.ACCEPTED and message_event:
            logger.info(
                "Slack webhook accepted tenant=%s %s event_id=%s user_id=%s",
                endpoint.tenant_id,
                endpoint_label,
                message_event.event_id,
                message_event.user_id,
            )
            await self.db.commit()
            asyncio.create_task(self.run_handle_message_background(message_event, endpoint.id))

        return SlackEventsIngressResult.from_admission(admission)

    async def process_interactions_webhook(
        self,
        *,
        endpoint_key: str,
        body_text: str,
        slack_timestamp: str,
        slack_signature: str,
    ) -> SlackInteractivityIngressResult:
        """Resolve endpoint, verify signature, and handle an interactivity POST."""
        auth = await authenticate_slack_webhook(
            self.repo,
            endpoint_key=endpoint_key,
            body_text=body_text,
            slack_timestamp=slack_timestamp,
            slack_signature=slack_signature,
        )
        if isinstance(auth, SlackWebhookAuthFailure):
            return SlackInteractivityIngressResult.auth_failed(auth)

        payload = parse_interactivity_payload(body_text)
        if not payload:
            return SlackInteractivityIngressResult.invalid_payload()

        response_body = await SlackInteractivityService(self.db).handle_payload(payload, auth)
        return SlackInteractivityIngressResult.handled(response_body)

    @staticmethod
    async def run_handle_message_background(event: SlackMessageEvent, endpoint_id: int) -> None:
        from apps.shared.db.session import app_db_session

        try:
            async with app_db_session() as bg_db:
                ingress = SlackIngressService(bg_db)
                await ingress.handle_message(event, endpoint_id)
        except Exception:
            logger.exception("Slack ingress background task failed for endpoint %s", endpoint_id)

    async def notify_disabled(self, event: SlackMessageEvent, endpoint_id: int) -> None:
        endpoint = await self._get_endpoint(endpoint_id)
        if not endpoint:
            return
        bot_token = self.repo.decrypt_bot_token(endpoint)
        await self._post_ephemeral(bot_token, event, SLACK_INTEGRATION_DISABLED_MESSAGE)

    async def notify_channel_chat_disabled(self, event: SlackMessageEvent, endpoint_id: int) -> None:
        """Tell the mentioner that channel chat is off.

        Use a thread reply for channel @mentions: ``chat.postEphemeral`` is only
        visible to one user and is easy to miss in the main channel view.
        """
        endpoint = await self._get_endpoint(endpoint_id)
        if not endpoint:
            return
        bot_token = self.repo.decrypt_bot_token(endpoint)
        text = SLACK_CHANNEL_CHAT_DISABLED_MESSAGE
        thread_ts = slack_reply_thread_ts(
            channel_type=event.channel_type,
            thread_ts=event.thread_ts,
            message_ts=event.ts,
        )
        try:
            await self.client.chat_post_message(
                bot_token=bot_token,
                channel=event.channel_id,
                text=text,
                thread_ts=thread_ts,
            )
        except Exception:
            logger.exception(
                "Failed to post channel-chat-disabled reply channel=%s user=%s",
                event.channel_id,
                event.user_id,
            )
            await self._post_ephemeral(bot_token, event, text)

    async def handle_message(self, event: SlackMessageEvent, endpoint_id: int) -> None:
        endpoint = await self._get_endpoint(endpoint_id)
        if not endpoint or not endpoint.enabled:
            logger.info("Slack ingress endpoint disabled or missing id=%s", endpoint_id)
            return
        if channel_chat_blocks_event(event, endpoint.platform_config):
            logger.info(
                "Slack channel chat disabled endpoint=%s event_id=%s source=%s",
                endpoint_id,
                event.event_id,
                event.source,
            )
            return

        tenant_id = endpoint.tenant_id
        bot_token = self.repo.decrypt_bot_token(endpoint)

        result = await self.identity_service.resolve_slack_user(
            tenant_id=tenant_id,
            slack_user_id=event.user_id,
            endpoint=endpoint,
        )
        if result is None:
            await self._post_ephemeral(bot_token, event, slack_user_message(SlackMessageKey.SLACK_VERIFY_FAILED))
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
            await self._post_ephemeral(bot_token, event, slack_user_message(SlackMessageKey.CHAT_PERMISSION_DENIED))
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

        # prepare/complete chat turns open their own committed sessions; persist the
        # Slack→chat thread mapping first so FK inserts can see chat_threads.
        await self.db.commit()

        message_text = strip_bot_mention(event.text, event.bot_user_id) if event.source == "app_mention" else event.text
        if not message_text.strip():
            await self._post_user_notice(
                bot_token,
                event,
                slack_user_message(SlackMessageKey.EMPTY_MENTION_MESSAGE),
            )
            return

        reply_thread_ts = slack_reply_thread_ts(
            channel_type=event.channel_type,
            thread_ts=event.thread_ts,
            message_ts=event.ts,
        )

        user_dto, tenant_name = await self._build_user_dto(tenant_id, result.user_id)
        if user_dto is None:
            await self._post_ephemeral(bot_token, event, slack_user_message(SlackMessageKey.LINKED_ACCOUNT_NOT_FOUND))
            return

        access_token = self.token_issuer.issue(
            user_id=user_dto.id,
            username=user_dto.username,
            role=user_dto.role,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )

        chat_request = ChatRequest(
            tenant_id=tenant_id,
            agent_id=agent_id,
            message=SimpleMessage(role="human", content=message_text),
            thread_id=thread_id,
        )

        async def _post_thinking(prepared: PreparedChatStream) -> str | None:
            thinking_text = slack_user_message(SlackMessageKey.THINKING_PLACEHOLDER)
            blocks = (
                build_thinking_placeholder_blocks(thinking_text=thinking_text, run_id=prepared.run_id)
                if prepared.run_id
                else None
            )
            thinking = await self.client.chat_post_message(
                bot_token=bot_token,
                channel=event.channel_id,
                text=thinking_text,
                thread_ts=reply_thread_ts,
                blocks=blocks,
            )
            return thinking.get("ts") if thinking else None

        try:
            turn = await run_slack_chat_turn(
                tenant_id,
                chat_request,
                user_dto,
                access_token,
                post_thinking_placeholder=_post_thinking,
            )
        except ThreadBusyError as exc:
            await self._post_ephemeral(bot_token, event, slack_chat_error_message(exc))
            return

        if turn.run_id:
            from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService

            if await ThreadRunService(self.db, tenant_id).is_run_cancelled(turn.run_id):
                logger.info(
                    "Skipping Slack reply delivery; run %s cancelled (thread %s)",
                    turn.run_id,
                    thread_id,
                )
                return

        message_id = turn.message_id
        session_id = turn.session_id
        thinking_ts = turn.thinking_ts
        reply_text = turn.reply_text

        reply_text = ensure_slack_reply_text(reply_text)
        settings = get_settings()

        message_id = await resolve_feedback_message_id(
            self.db,
            message_id=message_id,
            session_id=session_id,
            thread_id=thread_id,
        )
        delivery_kwargs = dict(
            client=self.client,
            bot_token=bot_token,
            channel_id=event.channel_id,
            text=reply_text,
            message_id=message_id,
            thread_ts=reply_thread_ts,
            db_session=self.db,
            update_ts=thinking_ts,
            portal_origin=settings.PORTAL_ORIGIN,
            api_origin=settings.TENANT_APP_API_ORIGIN,
            slack_user_id=event.user_id,
            channel_type=event.channel_type,
            tenant_id=tenant_id,
            requester_user_id=user_dto.id,
            requester_role=user_dto.role,
            agent_id=agent_id,
        )
        try:
            await post_slack_reply_with_feedback(**delivery_kwargs)
        except Exception:
            logger.exception(
                "Slack reply delivery failed for thread %s session %s; retrying once",
                thread_id,
                session_id,
            )
            await post_slack_reply_with_feedback(**delivery_kwargs)

    async def _get_endpoint(self, endpoint_id: int) -> AgentIngressEndpoint | None:
        result = await self.db.execute(select(AgentIngressEndpoint).where(AgentIngressEndpoint.id == endpoint_id))
        return result.scalar_one_or_none()

    async def _post_user_notice(self, bot_token: str, event: SlackMessageEvent, text: str) -> None:
        """User-visible feedback in shared channels; ephemeral in DMs."""
        if event.channel_type == "im":
            await self._post_ephemeral(bot_token, event, text)
            return
        thread_ts = slack_reply_thread_ts(
            channel_type=event.channel_type,
            thread_ts=event.thread_ts,
            message_ts=event.ts,
        )
        try:
            await self.client.chat_post_message(
                bot_token=bot_token,
                channel=event.channel_id,
                text=text,
                thread_ts=thread_ts,
            )
        except Exception:
            logger.exception("Failed to post Slack thread notice channel=%s user=%s", event.channel_id, event.user_id)
            await self._post_ephemeral(bot_token, event, text)

    async def _post_ephemeral(self, bot_token: str, event: SlackMessageEvent, text: str) -> None:
        try:
            await self.client.chat_post_ephemeral(
                bot_token=bot_token,
                channel=event.channel_id,
                user=event.user_id,
                text=text,
                thread_ts=slack_reply_thread_ts(
                    channel_type=event.channel_type,
                    thread_ts=event.thread_ts,
                    message_ts=event.ts,
                ),
            )
        except Exception:
            logger.exception("Failed to post Slack ephemeral to channel %s user %s", event.channel_id, event.user_id)

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
        thread_service = ThreadService(tenant_id, self.db)
        thread = await thread_service.get_thread(mapping.chat_thread_id)
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
        thread_service = ThreadService(tenant_id, self.db)
        return await thread_service.create_thread(
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
