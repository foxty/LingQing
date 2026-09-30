"""Public OIDC login flow service: start, callback, exchange.

Issues the same internal JWT as native login so downstream auth is unchanged.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.auth.membership_access import (
    LOGIN_BLOCKED_ACCOUNT_DISABLED,
    LOGIN_BLOCKED_MEMBERSHIP_INACTIVE,
    login_blocked_reason,
)
from apps.shared.core.exceptions import (
    AuthenticationError,
    ResourceNotFoundError,
)
from apps.shared.external_identity import (
    STATUS_ACTIVE,
    BindAction,
    ExtractedIdentity,
    IdentityBindingService,
)
from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository
from apps.shared.auth.oauth_pkce import generate_nonce, generate_pkce
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.auth.token import JwtTokenIssuer
from apps.tenant_app_service.sso.domain import (
    ProviderConfig,
    validate_provider_type,
)
from apps.tenant_app_service.sso.dtos import (
    SsoCallbackResult,
    SsoExchangeResponse,
    SsoStartResponse,
)
from apps.tenant_app_service.sso.providers import OidcAdapter, fetch_discovery
from apps.tenant_app_service.sso.repository import SsoRepository

logger = get_logger(__name__)

SSO_CALLBACK_PATH = "/auth/sso/callback"


class SsoLoginService:
    """Public OIDC login flow: start, callback, exchange."""

    def __init__(
        self,
        db: AsyncSession,
        adapter: OidcAdapter | None = None,
        token_issuer=None,
        binding_service: IdentityBindingService | None = None,
    ):
        self.db = db
        self.repo = SsoRepository(db)
        self.source_repo = IdentitySourceRepository(db)
        self.user_repo = UserRepository(db)
        self.binding_service = binding_service or IdentityBindingService(db)
        self.adapter = adapter or OidcAdapter()
        self.token_issuer = token_issuer or JwtTokenIssuer()
        self.settings = get_settings()

    def _redirect_uri(self) -> str:
        origin = self.settings.TENANT_APP_API_ORIGIN.rstrip("/")
        return f"{origin}{SSO_CALLBACK_PATH}"

    async def start(self, tenant_id: int, provider_id: int) -> SsoStartResponse:
        provider = await self.repo.get_provider(tenant_id, provider_id)
        if not provider or not provider.enabled:
            raise ResourceNotFoundError("Auth provider not found or disabled")
        validate_provider_type(provider.provider_type)

        decrypted = self.repo.decrypt_provider_config(provider)
        config = ProviderConfig(**decrypted)

        async with await self.adapter._with_client() as client:  # noqa: SLF001
            discovery = await fetch_discovery(config, http_client=client)
        config.authorize_endpoint = discovery.authorization_endpoint
        config.token_endpoint = discovery.token_endpoint
        config.userinfo_endpoint = discovery.userinfo_endpoint
        config.jwks_uri = discovery.jwks_uri

        state, code_verifier, code_challenge = generate_pkce()
        nonce = generate_nonce()
        await self.repo.create_login_state(
            tenant_id=tenant_id,
            provider_id=provider_id,
            state=state,
            code_verifier=code_verifier,
            nonce=nonce,
        )
        url = self.adapter.build_authorize_url(
            config=config,
            redirect_uri=self._redirect_uri(),
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
        )
        return SsoStartResponse(authorize_url=url)

    async def handle_callback(
        self,
        *,
        state: str,
        code: str,
        provider_id: int | None = None,
    ) -> SsoCallbackResult:
        login_state = await self.repo.consume_login_state(state)
        if not login_state:
            return SsoCallbackResult(status="denied", reason="invalid_or_expired_state")

        resolved_provider_id = login_state.provider_id
        if provider_id is not None and provider_id != resolved_provider_id:
            return SsoCallbackResult(status="denied", reason="provider_mismatch")

        tenant_id = login_state.tenant_id
        provider = await self.repo.get_provider(tenant_id, resolved_provider_id)
        if not provider or not provider.enabled:
            return SsoCallbackResult(status="denied", reason="provider_disabled")

        decrypted = self.repo.decrypt_provider_config(provider)
        config = ProviderConfig(**decrypted)
        async with await self.adapter._with_client() as client:  # noqa: SLF001
            discovery = await fetch_discovery(config, http_client=client)
        config.token_endpoint = discovery.token_endpoint
        config.userinfo_endpoint = discovery.userinfo_endpoint
        config.jwks_uri = discovery.jwks_uri

        try:
            token_response = await self.adapter.exchange_code(
                config=config,
                redirect_uri=self._redirect_uri(),
                code=code,
                code_verifier=login_state.code_verifier,
            )
            extracted = await self.adapter.extract_identity(
                config=config,
                token_response=token_response,
                expected_nonce=login_state.nonce,
            )
        except AuthenticationError as exc:
            logger.warning("OIDC callback failed: %s", exc)
            return SsoCallbackResult(status="denied", reason=str(exc))

        identity_source = await self.source_repo.get_by_id(tenant_id, provider.identity_source_id)
        if not identity_source:
            return SsoCallbackResult(status="denied", reason="identity_source_not_found")

        bind_result = await self.binding_service.resolve_or_bind(
            tenant_id=tenant_id,
            identity_source_id=identity_source.id,
            extracted=ExtractedIdentity(
                external_subject=extracted.external_subject,
                email=extracted.email,
                display_name=extracted.display_name,
            ),
            allowed_domains=await self._tenant_login_domains(tenant_id),
            policy=identity_source.bind_policy,
        )

        if bind_result.action == BindAction.LOGIN and bind_result.user_id is not None:
            return await self._issue_login_ticket(tenant_id=tenant_id, user_id=bind_result.user_id)
        if bind_result.action == BindAction.ATTACH and bind_result.user_id is not None:
            return await self._issue_login_ticket(tenant_id=tenant_id, user_id=bind_result.user_id)
        if bind_result.action == BindAction.JIT_CREATE:
            user = await self.user_repo.create_jit_member(
                tenant_id=tenant_id,
                email=extracted.email,
                display_name=extracted.display_name,
            )
            await self.repo.create_identity(
                tenant_id=tenant_id,
                identity_source_id=identity_source.id,
                external_subject=extracted.external_subject,
                user_id=user.id,
                email=extracted.email,
                display_name=extracted.display_name,
                status=STATUS_ACTIVE,
            )
            return await self._issue_login_ticket(tenant_id=tenant_id, user_id=user.id)
        if bind_result.action == BindAction.PENDING:
            return SsoCallbackResult(status="pending", reason=bind_result.reason)
        return SsoCallbackResult(status="denied", reason=bind_result.reason or "unknown")

    async def exchange_ticket(self, ticket: str) -> SsoExchangeResponse:
        row = await self.repo.consume_login_ticket(ticket)
        if not row:
            raise AuthenticationError("Invalid or expired SSO ticket", {"code": "SSO_INVALID_TICKET"})
        tenant = await self.repo.get_tenant(row.tenant_id)
        if not tenant:
            raise AuthenticationError("Tenant not found", {"code": "AUTH_TENANT_NOT_FOUND"})

        membership_row = await self.user_repo.get_user_membership(row.tenant_id, row.user_id)
        if not membership_row:
            raise AuthenticationError("User not found", {"code": "AUTH_USER_NOT_FOUND"})
        user, membership = membership_row
        blocked = login_blocked_reason(
            membership_status=membership.status,
            account_status=user.status,
        )
        if blocked == LOGIN_BLOCKED_MEMBERSHIP_INACTIVE:
            raise AuthenticationError("该用户已在当前租户停用", {"code": "AUTH_TENANT_DEACTIVATED"})
        if blocked == LOGIN_BLOCKED_ACCOUNT_DISABLED:
            raise AuthenticationError("该账号已被禁用", {"code": "AUTH_USER_DISABLED"})

        token = self.token_issuer.issue(
            user_id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        )
        await self.user_repo.update_last_login(user.id)
        return SsoExchangeResponse(
            access_token=token,
            token_type="bearer",
            user_id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        )

    async def _issue_login_ticket(self, *, tenant_id: int, user_id: int) -> SsoCallbackResult:
        membership_row = await self.user_repo.get_user_membership(tenant_id, user_id)
        if not membership_row:
            return SsoCallbackResult(status="denied", reason="user_not_found")
        user, membership = membership_row
        blocked = login_blocked_reason(
            membership_status=membership.status,
            account_status=user.status,
        )
        if blocked:
            return SsoCallbackResult(status="denied", reason=blocked)
        ticket = await self.repo.create_login_ticket(tenant_id=tenant_id, user_id=user_id)
        return SsoCallbackResult(status="success", ticket=ticket.ticket, user_id=user_id)

    async def _tenant_login_domains(self, tenant_id: int) -> list[str]:
        from apps.tenant_app_service.identity.services import IdentityAdminService

        return await IdentityAdminService(self.db).list_login_domain_names(tenant_id)
