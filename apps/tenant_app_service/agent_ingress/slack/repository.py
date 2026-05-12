"""Tenant-scoped repository for agent ingress endpoints and thread links."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentIngressEndpoint, IngressThreadLink, SlackProcessedEvent
from apps.shared.utils.field_cipher import FieldCipher
from apps.tenant_app_service.agent_ingress.slack.domain import slack_endpoint_scope_key

PLATFORM_SLACK = "slack"
_SLACK_SECRET_FIELDS = {"bot_token", "signing_secret"}
_DEDUPE_TTL_HOURS = 24


class SlackRepository:
    """Repository for Slack agent ingress endpoints, thread links, and dedupe."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cipher = FieldCipher()

    # ---------- Endpoint config ----------

    async def get_endpoint(self, tenant_id: int) -> AgentIngressEndpoint | None:
        """Return the first Slack endpoint for a tenant (legacy tenant-scoped admin API)."""
        result = await self.db.execute(
            select(AgentIngressEndpoint).where(
                AgentIngressEndpoint.tenant_id == tenant_id,
                AgentIngressEndpoint.platform == PLATFORM_SLACK,
            )
        )
        return result.scalars().first()

    async def get_endpoint_by_agent(self, tenant_id: int, agent_id: int) -> AgentIngressEndpoint | None:
        result = await self.db.execute(
            select(AgentIngressEndpoint).where(
                AgentIngressEndpoint.tenant_id == tenant_id,
                AgentIngressEndpoint.agent_id == agent_id,
                AgentIngressEndpoint.platform == PLATFORM_SLACK,
            )
        )
        return result.scalar_one_or_none()

    async def list_endpoints(self, tenant_id: int, *, platform: str = PLATFORM_SLACK) -> list[AgentIngressEndpoint]:
        result = await self.db.execute(
            select(AgentIngressEndpoint)
            .where(
                AgentIngressEndpoint.tenant_id == tenant_id,
                AgentIngressEndpoint.platform == platform,
            )
            .order_by(AgentIngressEndpoint.agent_id.asc())
        )
        return list(result.scalars().all())

    async def get_endpoint_by_key(self, endpoint_key: str) -> AgentIngressEndpoint | None:
        result = await self.db.execute(
            select(AgentIngressEndpoint).where(AgentIngressEndpoint.endpoint_key == endpoint_key)
        )
        return result.scalar_one_or_none()

    async def get_endpoint_by_team_id(
        self, team_id: str, *, app_id: str | None = None
    ) -> AgentIngressEndpoint | None:
        if app_id:
            scope_key = slack_endpoint_scope_key(team_id=team_id, app_id=app_id, tenant_id=0)
            result = await self.db.execute(
                select(AgentIngressEndpoint).where(
                    AgentIngressEndpoint.platform == PLATFORM_SLACK,
                    AgentIngressEndpoint.external_scope_key == scope_key,
                )
            )
            endpoint = result.scalar_one_or_none()
            if endpoint is not None:
                return endpoint
        result = await self.db.execute(
            select(AgentIngressEndpoint).where(
                AgentIngressEndpoint.platform == PLATFORM_SLACK,
                AgentIngressEndpoint.external_scope_key == f"slack:{team_id}",
            )
        )
        return result.scalar_one_or_none()

    async def create_endpoint(
        self,
        *,
        tenant_id: int,
        agent_id: int,
        bot_token: str,
        signing_secret: str,
        enabled: bool = False,
        team_id: str | None = None,
        team_name: str | None = None,
        app_id: str | None = None,
        bot_user_id: str | None = None,
        identity_source_id: int | None = None,
    ) -> AgentIngressEndpoint:
        credential_payload = {
            key: value
            for key, value in {
                "bot_token": bot_token,
                "signing_secret": signing_secret,
            }.items()
            if value
        }
        encrypted = self._cipher.encrypt_dict(
            credential_payload,
            sensitive_fields=_SLACK_SECRET_FIELDS,
        )
        platform_config: dict[str, str] = {}
        if team_id:
            platform_config["team_id"] = team_id
        if team_name:
            platform_config["team_name"] = team_name
        if app_id:
            platform_config["app_id"] = app_id
        if bot_user_id:
            platform_config["bot_user_id"] = bot_user_id
        row = AgentIngressEndpoint(
            tenant_id=tenant_id,
            agent_id=agent_id,
            platform=PLATFORM_SLACK,
            endpoint_key=secrets.token_urlsafe(32),
            external_scope_key=slack_endpoint_scope_key(
                team_id=team_id, app_id=app_id, tenant_id=tenant_id
            ),
            enabled=enabled,
            identity_source_id=identity_source_id,
            platform_config=platform_config,
            credentials_encrypted=encrypted,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_endpoint(
        self,
        endpoint: AgentIngressEndpoint,
        *,
        bot_token: str | None = None,
        signing_secret: str | None = None,
        agent_id: int | None = None,
        enabled: bool | None = None,
        team_id: str | None = None,
        team_name: str | None = None,
        app_id: str | None = None,
        bot_user_id: str | None = None,
    ) -> AgentIngressEndpoint:
        credentials = dict(endpoint.credentials_encrypted or {})
        if bot_token:
            credentials["bot_token"] = self._cipher.encrypt(bot_token)
        if signing_secret:
            credentials["signing_secret"] = self._cipher.encrypt(signing_secret)
        if bot_token or signing_secret:
            endpoint.credentials_encrypted = credentials
        if agent_id is not None:
            endpoint.agent_id = agent_id
        if enabled is not None:
            endpoint.enabled = enabled
        platform_config = dict(endpoint.platform_config or {})
        if team_id is not None:
            platform_config["team_id"] = team_id
        if team_name is not None:
            platform_config["team_name"] = team_name
        if app_id is not None:
            platform_config["app_id"] = app_id
        if bot_user_id is not None:
            platform_config["bot_user_id"] = bot_user_id
        if team_id is not None or team_name is not None or app_id is not None or bot_user_id is not None:
            endpoint.platform_config = platform_config
            endpoint.external_scope_key = slack_endpoint_scope_key(
                team_id=platform_config.get("team_id"),
                app_id=platform_config.get("app_id"),
                tenant_id=endpoint.tenant_id,
            )
        await self.db.flush()
        await self.db.refresh(endpoint)
        return endpoint

    async def delete_endpoint(self, endpoint: AgentIngressEndpoint) -> None:
        await self.db.delete(endpoint)
        await self.db.flush()

    def decrypt_bot_token(self, endpoint: AgentIngressEndpoint) -> str:
        token = (endpoint.credentials_encrypted or {}).get("bot_token", "")
        return self._cipher.decrypt(token) if token else ""

    def decrypt_signing_secret(self, endpoint: AgentIngressEndpoint) -> str:
        secret = (endpoint.credentials_encrypted or {}).get("signing_secret", "")
        return self._cipher.decrypt(secret) if secret else ""

    def slack_team_id(self, endpoint: AgentIngressEndpoint) -> str | None:
        return (endpoint.platform_config or {}).get("team_id")

    def slack_team_name(self, endpoint: AgentIngressEndpoint) -> str | None:
        return (endpoint.platform_config or {}).get("team_name")

    def slack_app_id(self, endpoint: AgentIngressEndpoint) -> str | None:
        return (endpoint.platform_config or {}).get("app_id")

    def slack_bot_user_id(self, endpoint: AgentIngressEndpoint) -> str | None:
        return (endpoint.platform_config or {}).get("bot_user_id")

    # ---------- Thread links ----------

    async def get_thread_link(
        self,
        tenant_id: int,
        external_channel_id: str,
        external_thread_key: str = "",
        *,
        endpoint_id: int,
    ) -> IngressThreadLink | None:
        """Resolve a thread link by endpoint conversation key.

        Lookup follows ``uq_ingress_thread_link`` (endpoint + channel + thread key).
        Agent is owned by the ingress endpoint, not duplicated on the link row.
        """
        result = await self.db.execute(
            select(IngressThreadLink).where(
                IngressThreadLink.tenant_id == tenant_id,
                IngressThreadLink.endpoint_id == endpoint_id,
                IngressThreadLink.external_channel_id == external_channel_id,
                IngressThreadLink.external_thread_key == external_thread_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_thread_link_by_chat_thread_id(
        self, tenant_id: int, chat_thread_id: str
    ) -> IngressThreadLink | None:
        result = await self.db.execute(
            select(IngressThreadLink).where(
                IngressThreadLink.tenant_id == tenant_id,
                IngressThreadLink.chat_thread_id == chat_thread_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_thread_link(
        self,
        *,
        tenant_id: int,
        endpoint_id: int,
        agent_id: int,
        external_user_id: str,
        external_channel_id: str,
        chat_thread_id: str,
        external_thread_key: str = "",
    ) -> IngressThreadLink:
        existing = await self.get_thread_link(
            tenant_id,
            external_channel_id,
            external_thread_key,
            endpoint_id=endpoint_id,
        )
        if existing is not None:
            return existing

        row = IngressThreadLink(
            tenant_id=tenant_id,
            endpoint_id=endpoint_id,
            agent_id=agent_id,
            external_user_id=external_user_id,
            external_channel_id=external_channel_id,
            external_thread_key=external_thread_key,
            chat_thread_id=chat_thread_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_thread_link(
        self,
        link: IngressThreadLink,
        *,
        chat_thread_id: str,
        agent_id: int,
    ) -> IngressThreadLink:
        link.chat_thread_id = chat_thread_id
        link.agent_id = agent_id
        await self.db.flush()
        await self.db.refresh(link)
        return link

    # ---------- Event dedupe ----------

    async def is_event_processed(self, tenant_id: int, event_id: str) -> bool:
        stmt = (
            pg_insert(SlackProcessedEvent)
            .values(tenant_id=tenant_id, event_id=event_id)
            .on_conflict_do_nothing(index_elements=["tenant_id", "event_id"])
            .returning(SlackProcessedEvent.id)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        return row is None

    async def cleanup_old_processed_events(self, hours: int = _DEDUPE_TTL_HOURS) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        result = await self.db.execute(
            delete(SlackProcessedEvent).where(SlackProcessedEvent.created_at < cutoff)
        )
        await self.db.flush()
        return result.rowcount or 0
