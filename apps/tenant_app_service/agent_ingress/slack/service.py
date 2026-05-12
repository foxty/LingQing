"""Application service for Slack ingress endpoint admin config."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort, SlackWebClient
from apps.tenant_app_service.agent_ingress.slack.domain import build_slack_app_manifest, slack_auth_metadata
from apps.tenant_app_service.agent_ingress.slack.dtos import (
    CreateAgentSlackIntegrationRequest,
    SlackIntegrationResponse,
    SlackTestConnectionResponse,
    UpdateAgentSlackIntegrationRequest,
)
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository

logger = get_logger(__name__)

INGRESS_EVENTS_PATH = "/ingress"


class SlackAdminService:
    """Admin operations: Slack endpoint CRUD and connection test."""

    def __init__(
        self,
        db: AsyncSession,
        client: SlackClientPort | None = None,
    ):
        self.db = db
        self.repo = SlackRepository(db)
        self.source_repo = SlackIdentitySourceRepository(db)
        self.client = client or SlackWebClient()
        self.settings = get_settings()

    async def get_integration_optional(
        self, tenant_id: int, agent_id: int
    ) -> SlackIntegrationResponse | None:
        endpoint = await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if not endpoint:
            return None
        return self._to_response(endpoint)

    async def get_integration(self, tenant_id: int, agent_id: int) -> SlackIntegrationResponse:
        integration = await self.get_integration_optional(tenant_id, agent_id)
        if not integration:
            raise ResourceNotFoundError("Slack integration not found for this agent")
        return integration

    async def list_integrations(self, tenant_id: int) -> list[SlackIntegrationResponse]:
        endpoints = await self.repo.list_endpoints(tenant_id)
        return [self._to_response(endpoint) for endpoint in endpoints]

    async def build_app_manifest_for_agent(
        self, tenant_id: int, agent_id: int, endpoint_key: str
    ) -> dict:
        agent_name = await self._agent_display_name(tenant_id, agent_id)
        events_url = self._events_url(endpoint_key)
        return build_slack_app_manifest(
            events_url=events_url,
            app_name=f"LingQing {agent_name}"[:35],
            bot_display_name=agent_name[:35],
        )

    async def ensure_provisioned_endpoint(
        self, tenant_id: int, agent_id: int
    ) -> AgentIngressEndpoint:
        """Ensure an ingress endpoint row exists so manifest Events URL is stable."""
        endpoint = await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if endpoint:
            return endpoint
        return await self.repo.create_endpoint(
            tenant_id=tenant_id,
            agent_id=agent_id,
            bot_token="",
            signing_secret="",
            enabled=False,
        )

    async def create_integration(
        self,
        tenant_id: int,
        agent_id: int,
        request: CreateAgentSlackIntegrationRequest,
    ) -> SlackIntegrationResponse:
        existing = await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if existing and self._credentials_configured(existing):
            raise ValidationError(
                "Slack integration already exists for this agent",
                {"code": "SLACK_INTEGRATION_EXISTS"},
            )

        test = await self.client.auth_test(bot_token=request.bot_token)
        if not test.get("ok"):
            raise ValidationError(
                "Slack bot token validation failed",
                {"code": "SLACK_INVALID_TOKEN", "error": test.get("error")},
            )

        team_id, app_id, bot_user_id = slack_auth_metadata(test)
        team_name = test.get("team")
        identity_source = await self._ensure_team_identity_source(
            tenant_id=tenant_id,
            team_id=team_id,
            team_name=team_name,
        )
        if existing:
            existing.identity_source_id = identity_source.id
            endpoint = await self.repo.update_endpoint(
                existing,
                bot_token=request.bot_token,
                signing_secret=request.signing_secret,
                enabled=request.enabled,
                team_id=team_id,
                team_name=team_name,
                app_id=app_id,
                bot_user_id=bot_user_id,
            )
        else:
            endpoint = await self.repo.create_endpoint(
                tenant_id=tenant_id,
                agent_id=agent_id,
                bot_token=request.bot_token,
                signing_secret=request.signing_secret,
                enabled=request.enabled,
                team_id=team_id,
                team_name=team_name,
                app_id=app_id,
                bot_user_id=bot_user_id,
                identity_source_id=identity_source.id,
            )
        logger.info(
            "Created Slack ingress endpoint for tenant %s agent %s (team=%s app=%s)",
            tenant_id,
            agent_id,
            team_id,
            app_id,
        )
        return self._to_response(endpoint)

    async def update_integration(
        self,
        tenant_id: int,
        agent_id: int,
        request: UpdateAgentSlackIntegrationRequest,
        *,
        endpoint: AgentIngressEndpoint | None = None,
    ) -> SlackIntegrationResponse:
        endpoint = endpoint or await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if not endpoint:
            raise ResourceNotFoundError("Slack integration not found for this agent")

        new_team_id: str | None = None
        new_team_name: str | None = None
        new_app_id: str | None = None
        new_bot_user_id: str | None = None
        if request.bot_token:
            test = await self.client.auth_test(bot_token=request.bot_token)
            if not test.get("ok"):
                raise ValidationError(
                    "Slack bot token validation failed",
                    {"code": "SLACK_INVALID_TOKEN", "error": test.get("error")},
                )
            new_team_id, new_app_id, new_bot_user_id = slack_auth_metadata(test)
            new_team_name = test.get("team")

        endpoint = await self.repo.update_endpoint(
            endpoint,
            bot_token=request.bot_token or None,
            signing_secret=request.signing_secret or None,
            enabled=request.enabled,
            team_id=new_team_id,
            team_name=new_team_name,
            app_id=new_app_id,
            bot_user_id=new_bot_user_id,
        )
        if new_team_id:
            team_source = await self._ensure_team_identity_source(
                tenant_id=tenant_id,
                team_id=new_team_id,
                team_name=new_team_name,
            )
            endpoint.identity_source_id = team_source.id
            await self.db.flush()
        return self._to_response(endpoint)

    async def delete_integration(self, tenant_id: int, agent_id: int) -> None:
        endpoint = await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if not endpoint:
            raise ResourceNotFoundError("Slack integration not found for this agent")
        await self.repo.delete_endpoint(endpoint)

    async def set_enabled(
        self,
        tenant_id: int,
        agent_id: int,
        enabled: bool,
        *,
        endpoint: AgentIngressEndpoint | None = None,
    ) -> SlackIntegrationResponse:
        endpoint = endpoint or await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if not endpoint:
            raise ResourceNotFoundError("Slack integration not found for this agent")
        endpoint = await self.repo.update_endpoint(endpoint, enabled=enabled)
        return self._to_response(endpoint)

    async def test_connection(
        self,
        tenant_id: int,
        agent_id: int,
        *,
        endpoint: AgentIngressEndpoint | None = None,
    ) -> SlackTestConnectionResponse:
        endpoint = endpoint or await self.repo.get_endpoint_by_agent(tenant_id, agent_id)
        if not endpoint:
            raise ResourceNotFoundError("Slack integration not found for this agent")
        bot_token = self.repo.decrypt_bot_token(endpoint)
        result = await self.client.auth_test(bot_token=bot_token)
        if result.get("ok"):
            team_id, app_id, bot_user_id = slack_auth_metadata(result)
            team_name = result.get("team")
            team_source = await self._ensure_team_identity_source(
                tenant_id=tenant_id,
                team_id=team_id,
                team_name=team_name,
            )
            endpoint = await self.repo.update_endpoint(
                endpoint,
                team_id=team_id,
                team_name=team_name,
                app_id=app_id,
                bot_user_id=bot_user_id,
            )
            endpoint.identity_source_id = team_source.id
            await self.db.flush()
            return SlackTestConnectionResponse(
                ok=True,
                team_id=result.get("team_id"),
                team_name=result.get("team"),
                bot_user_id=result.get("user_id"),
            )
        return SlackTestConnectionResponse(ok=False, error=result.get("error"))

    async def _ensure_team_identity_source(
        self,
        *,
        tenant_id: int,
        team_id: str,
        team_name: str | None,
    ):
        display_name = team_name or "Slack"
        team_source = await self.source_repo.ensure_slack_workspace_source(
            tenant_id=tenant_id,
            team_id=team_id,
            display_name=display_name,
        )
        await self.source_repo.consolidate_slack_tenant_placeholder(
            tenant_id=tenant_id,
            team_source=team_source,
        )
        return team_source

    async def _agent_display_name(self, tenant_id: int, agent_id: int) -> str:
        from apps.tenant_app_service.agent_catalog.domain import (
            SYSTEM_AGENT_ONE_ID,
            SYSTEM_AGENT_ONE_NAME,
        )
        from apps.tenant_app_service.agent_catalog.repository import AgentCatalogRepository

        if agent_id == SYSTEM_AGENT_ONE_ID:
            return SYSTEM_AGENT_ONE_NAME
        record = await AgentCatalogRepository(self.db).get_by_id_and_tenant(agent_id, tenant_id)
        return record.name if record else f"Agent {agent_id}"

    @staticmethod
    def _credentials_configured(endpoint: AgentIngressEndpoint) -> bool:
        credentials = endpoint.credentials_encrypted or {}
        return bool(credentials.get("bot_token")) and bool(credentials.get("signing_secret"))

    def _to_response(self, endpoint: AgentIngressEndpoint) -> SlackIntegrationResponse:
        return SlackIntegrationResponse(
            id=endpoint.id,
            tenant_id=endpoint.tenant_id,
            agent_id=endpoint.agent_id,
            slack_team_id=self.repo.slack_team_id(endpoint),
            slack_team_name=self.repo.slack_team_name(endpoint),
            slack_app_id=self.repo.slack_app_id(endpoint),
            bot_user_id=self.repo.slack_bot_user_id(endpoint),
            bot_token_configured=bool((endpoint.credentials_encrypted or {}).get("bot_token")),
            signing_secret_configured=bool((endpoint.credentials_encrypted or {}).get("signing_secret")),
            default_agent_id=endpoint.agent_id,
            enabled=endpoint.enabled,
            endpoint_key=endpoint.endpoint_key,
            events_url=self._events_url(endpoint.endpoint_key),
        )

    def _events_url(self, endpoint_key: str) -> str:
        origin = self.settings.TENANT_APP_API_ORIGIN.rstrip("/")
        return f"{origin}{INGRESS_EVENTS_PATH}/{endpoint_key}/events"
