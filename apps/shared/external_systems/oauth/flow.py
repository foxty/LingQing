"""Application flow for user-scoped API connector OAuth."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.config import get_settings
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.adapters import connector_entity_to_domain
from apps.shared.external_systems.api_connector.domain import OAuth2AuthConfig
from apps.shared.external_systems.api_connector.repository import ApiConnectorRepository
from apps.shared.external_systems.credentials.dtos import (
    UserIntegrationConnectionResponse,
    UserIntegrationConnectionUpsertRequest,
)
from apps.shared.external_systems.credentials.service import UserIntegrationCredentialService
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER
from apps.shared.external_systems.oauth.state import OAuthStateCodec
from apps.shared.infra.oauth import OAuth2TokenClient
from apps.shared.utils.field_cipher import FieldCipher

# Shared browser callback on the API (not per-connector). Slack Redirect URL registers this once.
OAUTH_CALLBACK_PATH = "/api-connectors/oauth/callback"


class ApiConnectorOAuthFlow:
    def __init__(
        self,
        db_session,
        *,
        token_client: OAuth2TokenClient | None = None,
        state_codec: OAuthStateCodec | None = None,
    ) -> None:
        self._db = db_session
        self._repo = ApiConnectorRepository(db_session)
        self._cipher = FieldCipher()
        self._token_client = token_client or OAuth2TokenClient()
        self._state_codec = state_codec or OAuthStateCodec(self._cipher)

    async def start(self, *, actor: ActorContext, connector_id: int) -> str:
        config = await self._oauth_config(actor=actor, connector_id=connector_id)
        redirect_uri = config.redirect_uri or self._default_redirect_uri()
        state, verifier = self._state_codec.issue(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            connector_id=connector_id,
            redirect_uri=redirect_uri,
        )
        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": self._state_codec.code_challenge(verifier),
            "code_challenge_method": "S256",
        }
        if config.scopes:
            params[config.scope_param] = " ".join(config.scopes)
        return self._append_query(config.authorize_url, params)

    async def complete(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
        code: str,
        state: str,
    ) -> UserIntegrationConnectionResponse:
        decoded = self._state_codec.decode(state)
        if (
            decoded.tenant_id != actor.tenant_id
            or decoded.user_id != actor.user_id
            or decoded.connector_id != connector_id
        ):
            raise ValidationError("OAuth state does not match the current user or connector")

        config = await self._oauth_config(actor=actor, connector_id=connector_id)
        tokens = await self._token_client.exchange_code(
            config=config,
            code=code,
            code_verifier=decoded.code_verifier,
            redirect_uri=decoded.redirect_uri,
        )
        credential_service = UserIntegrationCredentialService(self._db)
        return await credential_service.upsert_api_connector_connection(
            actor=actor,
            connector_id=connector_id,
            body=UserIntegrationConnectionUpsertRequest(
                auth_type="oauth2",
                secrets=tokens.to_secrets(),
                expires_at=tokens.expires_at,
            ),
        )

    async def complete_from_callback(self, *, code: str, state: str) -> int:
        """Complete OAuth from the shared browser callback using encrypted state (no session)."""
        decoded = self._state_codec.decode(state)
        actor = ActorContext(
            tenant_id=decoded.tenant_id,
            user_id=decoded.user_id,
            user_role="member",
        )
        await self.complete(
            actor=actor,
            connector_id=decoded.connector_id,
            code=code,
            state=state,
        )
        return decoded.connector_id

    async def _oauth_config(self, *, actor: ActorContext, connector_id: int) -> OAuth2AuthConfig:
        connector = await self._repo.get_by_id_and_tenant(connector_id, actor.tenant_id)
        if connector is None:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")
        if connector.auth_type != "oauth2" or connector.credential_mode != CREDENTIAL_MODE_USER:
            raise ValidationError("API connector is not configured for user OAuth2")
        domain = connector_entity_to_domain(connector, cipher=self._cipher)
        if not isinstance(domain.auth_config, OAuth2AuthConfig):
            raise ValidationError("Invalid OAuth2 connector configuration")
        return domain.auth_config

    @staticmethod
    def _default_redirect_uri() -> str:
        return f"{get_settings().TENANT_APP_API_ORIGIN.rstrip('/')}{OAUTH_CALLBACK_PATH}"

    @staticmethod
    def portal_success_url(connector_id: int) -> str:
        return f"{get_settings().PORTAL_ORIGIN.rstrip('/')}/api-connectors/{connector_id}?oauth=connected"

    @staticmethod
    def portal_error_url(*, connector_id: int | None = None) -> str:
        portal = get_settings().PORTAL_ORIGIN.rstrip("/")
        if connector_id is not None:
            return f"{portal}/api-connectors/{connector_id}?oauth=error"
        return f"{portal}/api-connectors?oauth=error"

    @staticmethod
    def _append_query(url: str, params: dict[str, str]) -> str:
        parts = urlsplit(url)
        query = [*parse_qsl(parts.query, keep_blank_values=True), *params.items()]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
