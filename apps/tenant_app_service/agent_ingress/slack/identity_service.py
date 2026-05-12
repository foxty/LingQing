"""Slack identity mapping service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.external_identity import (
    BindAction,
    ExtractedIdentity,
    IdentityBindingResult,
    IdentityBindingService,
)
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository

logger = get_logger(__name__)


class SlackIdentityService:
    """Resolve Slack users to internal users via email auto-match."""

    def __init__(
        self,
        db: AsyncSession,
        client=None,
        binding_service: IdentityBindingService | None = None,
    ):
        self.db = db
        self.client = client
        self.binding_service = binding_service or IdentityBindingService(db)
        self.repo = SlackRepository(db)
        self.source_repo = SlackIdentitySourceRepository(db)

    async def resolve_slack_user(
        self,
        *,
        tenant_id: int,
        slack_user_id: str,
        endpoint: AgentIngressEndpoint,
    ) -> IdentityBindingResult | None:
        identity_source = None
        if endpoint.identity_source_id is not None:
            identity_source = await self.source_repo.get_by_id(tenant_id, endpoint.identity_source_id)
        if not identity_source:
            team_id = self.repo.slack_team_id(endpoint)
            if not team_id:
                logger.warning(
                    "Slack endpoint %s has no workspace identity source or team_id",
                    endpoint.id,
                )
                return None
            team_name = self.repo.slack_team_name(endpoint)
            identity_source = await self.source_repo.ensure_slack_workspace_source(
                tenant_id=tenant_id,
                team_id=team_id,
                display_name=team_name or "Slack",
            )
            endpoint.identity_source_id = identity_source.id
            await self.db.flush()

        active = await self.binding_service.get_active_binding(
            tenant_id=tenant_id,
            identity_source_id=identity_source.id,
            external_subject=slack_user_id,
        )
        if active and active.action == BindAction.LOGIN and active.user_id is not None:
            return active

        if self.client is None:
            from apps.tenant_app_service.agent_ingress.slack.client import SlackWebClient

            self.client = SlackWebClient()

        bot_token = self.repo.decrypt_bot_token(endpoint)
        user_profile = await self.client.users_info(bot_token=bot_token, user_id=slack_user_id)
        if not user_profile:
            logger.warning("Slack users.info failed for %s in tenant %s", slack_user_id, tenant_id)
            return None

        profile = user_profile.get("profile") or {}
        email = profile.get("email")
        display_name = profile.get("display_name") or user_profile.get("name") or slack_user_id

        extracted = ExtractedIdentity(
            external_subject=slack_user_id,
            email=email,
            display_name=display_name,
        )

        allowed_domains = await self._tenant_login_domains(tenant_id)

        return await self.binding_service.resolve_or_bind(
            tenant_id=tenant_id,
            identity_source_id=identity_source.id,
            extracted=extracted,
            allowed_domains=allowed_domains,
            policy=identity_source.bind_policy,
        )

    async def _tenant_login_domains(self, tenant_id: int) -> list[str]:
        from apps.tenant_app_service.identity.services import IdentityAdminService

        return await IdentityAdminService(self.db).list_login_domain_names(tenant_id)
