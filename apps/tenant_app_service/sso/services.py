"""Application services for tenant SSO (OIDC providers and login flow helpers)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.core.exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.models import AuthProvider, Tenant
from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository
from apps.tenant_app_service.identity.repository import IdentityRepository
from apps.tenant_app_service.sso.domain import (
    LOGIN_METHOD_NATIVE,
    PROVIDER_TYPE_OIDC,
    validate_policy,
    validate_provider_type,
)
from apps.tenant_app_service.sso.dtos import (
    AuthProviderResponse,
    CreateAuthProviderRequest,
    LoginMethodDTO,
    ProviderConfigResponseDTO,
    ResolveTenantMethodsResponse,
    UpdateAuthProviderRequest,
)
from apps.tenant_app_service.sso.repository import SsoRepository

SSO_CALLBACK_PATH = "/auth/sso/callback"


class SsoAdminService:
    """OIDC provider CRUD and tenant login method resolution."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SsoRepository(db)
        self.identity_repo = IdentityRepository(db)
        self.source_repo = IdentitySourceRepository(db)
        self.settings = get_settings()

    async def list_providers(self, tenant_id: int) -> list[AuthProviderResponse]:
        providers = await self.repo.list_providers(tenant_id)
        out: list[AuthProviderResponse] = []
        for provider in providers:
            out.append(await self._to_response(provider))
        return out

    async def get_provider(self, tenant_id: int, provider_id: int) -> AuthProviderResponse:
        provider = await self.repo.get_provider(tenant_id, provider_id)
        if not provider:
            raise ResourceNotFoundError("Auth provider not found")
        return await self._to_response(provider)

    async def create_provider(self, tenant_id: int, request: CreateAuthProviderRequest) -> AuthProviderResponse:
        validate_provider_type(request.provider_type)
        validate_policy(request.first_login_policy)
        if await self.repo.get_provider_by_name(tenant_id, request.display_name):
            raise DuplicateResourceError(
                "Provider display_name already exists in this tenant",
                {"code": "SSO_PROVIDER_DUPLICATE"},
            )
        config = request.config.model_dump()
        source = await self.source_repo.create_login_provider_source(
            tenant_id=tenant_id,
            display_name=request.display_name,
            bind_policy=request.first_login_policy,
        )
        provider = await self.repo.create_provider(
            tenant_id=tenant_id,
            provider_type=request.provider_type,
            display_name=request.display_name,
            enabled=request.enabled,
            config=config,
            identity_source_id=source.id,
        )
        await self.source_repo.finalize_login_provider_source_key(source, provider.id)
        return await self._to_response(provider)

    async def update_provider(
        self, tenant_id: int, provider_id: int, request: UpdateAuthProviderRequest
    ) -> AuthProviderResponse:
        provider = await self.repo.get_provider(tenant_id, provider_id)
        if not provider:
            raise ResourceNotFoundError("Auth provider not found")

        if request.display_name is not None and request.display_name != provider.display_name:
            if await self.repo.get_provider_by_name(tenant_id, request.display_name):
                raise DuplicateResourceError(
                    "Provider display_name already exists in this tenant",
                    {"code": "SSO_PROVIDER_DUPLICATE"},
                )
            provider.display_name = request.display_name

        if request.enabled is not None:
            provider.enabled = request.enabled

        if request.first_login_policy is not None:
            validate_policy(request.first_login_policy)
            await self.source_repo.update_bind_policy(
                tenant_id, provider.identity_source_id, request.first_login_policy
            )

        if request.display_name is not None:
            source = await self.source_repo.get_by_id(tenant_id, provider.identity_source_id)
            if source:
                await self.source_repo.sync_display_name(source, request.display_name)

        if request.config is not None:
            new_config = request.config.model_dump()
            existing_decrypted = self.repo.decrypt_provider_config(provider)
            if not new_config.get("client_secret"):
                new_config["client_secret"] = existing_decrypted.get("client_secret", "")
            provider.config_json = self.repo.encrypt_config(new_config)

        provider = await self.repo.update_provider(provider)
        return await self._to_response(provider)

    async def delete_provider(self, tenant_id: int, provider_id: int) -> None:
        provider = await self.repo.get_provider(tenant_id, provider_id)
        if not provider:
            raise ResourceNotFoundError("Auth provider not found")
        source_id = provider.identity_source_id
        await self.repo.delete_provider(provider)
        source = await self.source_repo.get_by_id(tenant_id, source_id)
        if source:
            await self.db.delete(source)
            await self.db.flush()

    async def set_provider_enabled(self, tenant_id: int, provider_id: int, enabled: bool) -> AuthProviderResponse:
        provider = await self.repo.get_provider(tenant_id, provider_id)
        if not provider:
            raise ResourceNotFoundError("Auth provider not found")
        provider.enabled = enabled
        provider = await self.repo.update_provider(provider)
        return await self._to_response(provider)

    async def resolve_login_methods(self, tenant: Tenant) -> list[LoginMethodDTO]:
        methods: list[LoginMethodDTO] = []
        if not getattr(tenant, "force_sso", False):
            methods.append(LoginMethodDTO(type=LOGIN_METHOD_NATIVE))
        providers = await self.repo.list_providers(tenant.id)
        for provider in providers:
            if provider.enabled and provider.provider_type == PROVIDER_TYPE_OIDC:
                issuer = self.repo.decrypt_provider_config(provider).get("issuer", "")
                methods.append(
                    LoginMethodDTO(
                        type=PROVIDER_TYPE_OIDC,
                        provider_id=provider.id,
                        display_name=provider.display_name,
                        issuer=issuer or None,
                    )
                )
        return methods

    async def resolve_tenant_methods(self, identifier: str) -> ResolveTenantMethodsResponse:
        tenant, _identity = await self._resolve_tenant(identifier)
        methods = await self.resolve_login_methods(tenant)
        force_sso = bool(getattr(tenant, "force_sso", False))
        break_glass_count = (
            await self.identity_repo.count_break_glass_admins(tenant.id) if force_sso else 0
        )
        return ResolveTenantMethodsResponse(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug or "",
            login_methods=methods,
            force_sso=force_sso,
            emergency_password_available=force_sso and break_glass_count > 0,
        )

    async def _resolve_tenant(self, identifier: str) -> tuple[Tenant, str]:
        if "@" not in identifier:
            raise ValidationError(
                "Invalid sign-in identifier",
                {"code": "AUTH_IDENTIFIER_INVALID"},
            )
        user_identity, tenant_part = identifier.rsplit("@", 1)
        if not user_identity or not tenant_part:
            raise ValidationError(
                "Invalid sign-in identifier",
                {"code": "AUTH_IDENTIFIER_INVALID"},
            )
        if "." in tenant_part:
            domain = tenant_part.lower()
            domain_row = await self.identity_repo.get_domain(domain)
            if domain_row:
                tenant = await self.identity_repo.get_tenant(domain_row.tenant_id)
                if tenant:
                    return tenant, user_identity
            raise ValidationError(
                "Tenant not found for identifier",
                {"code": "AUTH_TENANT_NOT_FOUND", "domain": domain},
            )

        from apps.tenant_app_service.tenant.repository import TenantRepository

        tenant_repo = TenantRepository(self.db)
        tenant = await tenant_repo.get_by_slug(tenant_part)
        if not tenant:
            raise ValidationError(
                "Tenant not found for identifier",
                {"code": "AUTH_TENANT_NOT_FOUND", "slug": tenant_part},
            )
        return tenant, user_identity

    async def _to_response(self, provider: AuthProvider) -> AuthProviderResponse:
        source = await self.source_repo.get_by_id(provider.tenant_id, provider.identity_source_id)
        bind_policy = source.bind_policy if source else "jit_create"
        decrypted = self.repo.decrypt_provider_config(provider)
        config = ProviderConfigResponseDTO(
            client_id=decrypted.get("client_id", ""),
            client_secret_configured=bool(decrypted.get("client_secret")),
            issuer=decrypted.get("issuer", ""),
            scopes=decrypted.get("scopes", ["openid", "email", "profile"]),
            extra_authorize_params=decrypted.get("extra_authorize_params", {}),
            authorize_endpoint=decrypted.get("authorize_endpoint"),
            token_endpoint=decrypted.get("token_endpoint"),
            userinfo_endpoint=decrypted.get("userinfo_endpoint"),
            jwks_uri=decrypted.get("jwks_uri"),
        )
        return AuthProviderResponse(
            id=provider.id,
            tenant_id=provider.tenant_id,
            provider_type=provider.provider_type,
            display_name=provider.display_name,
            enabled=provider.enabled,
            config=config,
            first_login_policy=bind_policy,
            callback_url=self._callback_url(),
        )

    def _callback_url(self) -> str:
        origin = self.settings.TENANT_APP_API_ORIGIN.rstrip("/")
        return f"{origin}{SSO_CALLBACK_PATH}"
