"""Application flow for user-scoped integration OAuth (API connectors, data sources)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from apps.config import get_settings
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.api_connector.adapters import connector_entity_to_domain
from apps.shared.external_systems.api_connector.domain import OAuth2AuthConfig
from apps.shared.external_systems.api_connector.repository import ApiConnectorRepository
from apps.shared.external_systems.credentials.dtos import UserIntegrationConnectionUpsertRequest
from apps.shared.external_systems.credentials.service import UserIntegrationCredentialService
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER
from apps.shared.external_systems.oauth.state import OAuthStateCodec
from apps.shared.infra.oauth import (
    TOKEN_AUTH_METHOD_CLIENT_SECRET_POST,
    OAuth2TokenClient,
    OAuthTokenSet,
    build_authorize_url,
)
from apps.shared.utils.field_cipher import FieldCipher

# Canonical shared browser callback on the API (registered once per IdP OAuth app).
INTEGRATION_OAUTH_CALLBACK_PATH = "/integrations/oauth/callback"


@dataclass(frozen=True)
class OAuthAuthorizationSpec:
    """Resource-agnostic OAuth 2.0 client + endpoint configuration."""

    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str | None = None
    scopes: tuple[str, ...] = ()
    scope_param: str = "scope"
    redirect_uri: str | None = None
    token_auth_method: str = TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
    token_response_path: str | None = None
    extra_authorize_params: Mapping[str, str] | None = None


@dataclass(frozen=True)
class OAuthCallbackOutcome:
    """Resolved resource and portal destination after completing browser OAuth."""

    resource_type: str
    resource_id: int
    portal_url: str


class IntegrationOAuthTarget(Protocol):
    """Per-resource-type adapter plugged into ``IntegrationOAuthFlow``."""

    resource_type: str

    async def load_oauth_spec(self, *, actor: ActorContext, resource_id: int) -> OAuthAuthorizationSpec: ...

    async def save_tokens(
        self,
        *,
        actor: ActorContext,
        resource_id: int,
        tokens: OAuthTokenSet,
    ) -> None: ...

    def portal_success_url(self, resource_id: int) -> str: ...

    def portal_error_url(self, *, resource_id: int | None = None) -> str: ...


class ApiConnectorOAuthTarget:
    """``IntegrationOAuthTarget`` implementation for user-mode OAuth2 API connectors."""

    resource_type = RESOURCE_TYPE_API_CONNECTOR

    def __init__(self, db_session, *, cipher: FieldCipher | None = None) -> None:
        self._db = db_session
        self._repo = ApiConnectorRepository(db_session)
        self._cipher = cipher or FieldCipher()

    async def load_oauth_config(self, *, actor: ActorContext, connector_id: int) -> OAuth2AuthConfig:
        connector = await self._repo.get_by_id_and_tenant(connector_id, actor.tenant_id)
        if connector is None:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")
        if connector.auth_type != "oauth2" or connector.credential_mode != CREDENTIAL_MODE_USER:
            raise ValidationError("API connector is not configured for user OAuth2")
        domain = connector_entity_to_domain(connector, cipher=self._cipher)
        if not isinstance(domain.auth_config, OAuth2AuthConfig):
            raise ValidationError("Invalid OAuth2 connector configuration")
        return domain.auth_config

    async def load_oauth_spec(self, *, actor: ActorContext, resource_id: int) -> OAuthAuthorizationSpec:
        config = await self.load_oauth_config(actor=actor, connector_id=resource_id)
        return self.spec_from_connector_config(config)

    @staticmethod
    def spec_from_connector_config(config: OAuth2AuthConfig) -> OAuthAuthorizationSpec:
        return OAuthAuthorizationSpec(
            authorize_url=config.authorize_url,
            token_url=config.token_url,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scopes=tuple(config.scopes or ()),
            scope_param=config.scope_param,
            redirect_uri=config.redirect_uri
            or (f"{get_settings().TENANT_APP_API_ORIGIN.rstrip('/')}{INTEGRATION_OAUTH_CALLBACK_PATH}"),
            token_auth_method=config.token_auth_method,
            token_response_path=config.token_response_path,
        )

    async def save_tokens(
        self,
        *,
        actor: ActorContext,
        resource_id: int,
        tokens: OAuthTokenSet,
    ) -> None:
        credential_service = UserIntegrationCredentialService(self._db)
        await credential_service.upsert_api_connector_connection(
            actor=actor,
            connector_id=resource_id,
            body=UserIntegrationConnectionUpsertRequest(
                auth_type="oauth2",
                secrets=tokens.to_secrets(),
                expires_at=tokens.expires_at,
            ),
        )

    @staticmethod
    def portal_success_url(resource_id: int) -> str:
        return f"{get_settings().PORTAL_ORIGIN.rstrip('/')}/api-connectors/{resource_id}?oauth=connected"

    @staticmethod
    def portal_error_url(*, resource_id: int | None = None) -> str:
        portal = get_settings().PORTAL_ORIGIN.rstrip("/")
        if resource_id is not None:
            return f"{portal}/api-connectors/{resource_id}?oauth=error"
        return f"{portal}/api-connectors?oauth=error"


class IntegrationOAuthFlow:
    """Resource-typed OAuth 2.0 Authorization Code + PKCE coordinator."""

    def __init__(
        self,
        db_session,
        *,
        token_client: OAuth2TokenClient | None = None,
        state_codec: OAuthStateCodec | None = None,
        targets: Mapping[str, IntegrationOAuthTarget] | None = None,
    ) -> None:
        self._db = db_session
        self._cipher = FieldCipher()
        self._token_client = token_client or OAuth2TokenClient()
        self._state_codec = state_codec or OAuthStateCodec(self._cipher)
        if targets is not None:
            self._targets = dict(targets)
        else:
            self._targets = {
                RESOURCE_TYPE_API_CONNECTOR: ApiConnectorOAuthTarget(db_session, cipher=self._cipher),
            }

    def _require_target(self, resource_type: str) -> IntegrationOAuthTarget:
        target = self._targets.get(resource_type)
        if target is None:
            raise ValidationError(f"Unsupported OAuth integration resource_type: {resource_type}")
        return target

    async def start(
        self,
        *,
        actor: ActorContext,
        resource_type: str,
        resource_id: int,
    ) -> str:
        target = self._require_target(resource_type)
        spec = await target.load_oauth_spec(actor=actor, resource_id=resource_id)
        redirect_uri = spec.redirect_uri or self.default_redirect_uri()
        state, verifier = self._state_codec.issue(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            redirect_uri=redirect_uri,
        )
        return build_authorize_url(
            spec.authorize_url,
            client_id=spec.client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=self._state_codec.code_challenge(verifier),
            scopes=spec.scopes,
            scope_param=spec.scope_param,
            extra_params=spec.extra_authorize_params,
        )

    async def complete(
        self,
        *,
        actor: ActorContext,
        resource_type: str,
        resource_id: int,
        code: str,
        state: str,
    ) -> None:
        decoded = self._state_codec.decode(state)
        if (
            decoded.tenant_id != actor.tenant_id
            or decoded.user_id != actor.user_id
            or decoded.resource_type != resource_type
            or decoded.resource_id != resource_id
        ):
            raise ValidationError("OAuth state does not match the current user or resource")

        target = self._require_target(resource_type)
        spec = await target.load_oauth_spec(actor=actor, resource_id=resource_id)
        tokens = await self._token_client.exchange_code(
            config=spec,
            code=code,
            code_verifier=decoded.code_verifier,
            redirect_uri=decoded.redirect_uri,
        )
        await target.save_tokens(actor=actor, resource_id=resource_id, tokens=tokens)

    async def complete_from_callback(self, *, code: str, state: str) -> OAuthCallbackOutcome:
        """Complete OAuth from the shared browser callback using encrypted state (no session)."""
        decoded = self._state_codec.decode(state)
        target = self._require_target(decoded.resource_type)
        actor = ActorContext(
            tenant_id=decoded.tenant_id,
            user_id=decoded.user_id,
            user_role="member",
        )
        await self.complete(
            actor=actor,
            resource_type=decoded.resource_type,
            resource_id=decoded.resource_id,
            code=code,
            state=state,
        )
        return OAuthCallbackOutcome(
            resource_type=decoded.resource_type,
            resource_id=decoded.resource_id,
            portal_url=target.portal_success_url(decoded.resource_id),
        )

    def portal_error_url_for_state(
        self,
        state: str | None,
        *,
        default_resource_type: str = RESOURCE_TYPE_API_CONNECTOR,
    ) -> str:
        resource_type = default_resource_type
        resource_id: int | None = None
        if state:
            try:
                decoded = self._state_codec.decode(state)
                resource_type = decoded.resource_type
                resource_id = decoded.resource_id
            except ValidationError:
                resource_id = None
        target = self._targets.get(resource_type) or self._targets.get(default_resource_type)
        if target is None:
            return f"{get_settings().PORTAL_ORIGIN.rstrip('/')}/?oauth=error"
        return target.portal_error_url(resource_id=resource_id)

    @staticmethod
    def default_redirect_uri() -> str:
        return f"{get_settings().TENANT_APP_API_ORIGIN.rstrip('/')}{INTEGRATION_OAUTH_CALLBACK_PATH}"
