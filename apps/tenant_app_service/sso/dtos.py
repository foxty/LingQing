"""DTOs for tenant SSO admin and login APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.shared.external_identity.domain import (
    POLICY_JIT,
    FirstLoginPolicy,
)
from apps.tenant_app_service.sso.domain import PROVIDER_TYPE_OIDC, ProviderType


class ProviderConfigDTO(BaseModel):
    """OIDC provider config. `client_secret` is write-only."""

    client_id: str = Field(..., min_length=1, description="OAuth client id")
    client_secret: str = Field(
        default="",
        description="OAuth client secret. Send empty string on update to keep previous value.",
    )
    issuer: str = Field(..., min_length=1, description="OIDC issuer URL, e.g. https://accounts.google.com")
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    extra_authorize_params: dict[str, str] = Field(default_factory=dict)
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None


class ProviderConfigResponseDTO(BaseModel):
    """OIDC provider config for responses. Never includes the secret."""

    client_id: str
    client_secret_configured: bool
    issuer: str
    scopes: list[str]
    extra_authorize_params: dict[str, str]
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None


class CreateAuthProviderRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)
    provider_type: ProviderType = Field(default=PROVIDER_TYPE_OIDC)
    enabled: bool = False
    config: ProviderConfigDTO
    first_login_policy: FirstLoginPolicy = Field(default=POLICY_JIT)


class UpdateAuthProviderRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    config: ProviderConfigDTO | None = None
    first_login_policy: FirstLoginPolicy | None = None


class AuthProviderResponse(BaseModel):
    id: int
    tenant_id: int
    provider_type: ProviderType
    display_name: str
    enabled: bool
    config: ProviderConfigResponseDTO
    first_login_policy: FirstLoginPolicy
    callback_url: str


class LoginMethodDTO(BaseModel):
    type: str
    provider_id: int | None = None
    display_name: str | None = None
    issuer: str | None = None


class ResolveTenantMethodsRequest(BaseModel):
    identifier: str


class ResolveTenantMethodsResponse(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    login_methods: list[LoginMethodDTO]
    force_sso: bool = False
    emergency_password_available: bool = False


class SsoStartResponse(BaseModel):
    authorize_url: str


class SsoExchangeRequest(BaseModel):
    ticket: str


class SsoExchangeResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    role: str
    tenant_id: int
    tenant_name: str


class SsoCallbackResult(BaseModel):
    """Result of processing an OIDC callback (used internally + tests)."""

    status: str
    ticket: str | None = None
    reason: str | None = None
    user_id: int | None = None
