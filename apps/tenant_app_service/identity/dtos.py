"""DTOs for tenant identity admin APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from apps.shared.external_identity.domain import (
    POLICY_JIT,
    FirstLoginPolicy,
    IdentityStatus,
)


class IdentitySettingsResponse(BaseModel):
    force_sso: bool
    break_glass_admin_count: int


class UpdateIdentitySettingsRequest(BaseModel):
    force_sso: bool


class BreakGlassRequest(BaseModel):
    is_break_glass: bool


class LoginDomainRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1)

    @field_validator("domains")
    @classmethod
    def _normalize(cls, v: list[str]) -> list[str]:
        return [d.strip().lower() for d in v if d.strip()]


class LoginDomainResponse(BaseModel):
    id: int
    tenant_id: int
    domain: str


class IdentitySourceResponse(BaseModel):
    id: int
    tenant_id: int
    source_kind: str
    source_key: str
    display_name: str
    bind_policy: FirstLoginPolicy
    linked_auth_provider_id: int | None = None
    linked_slack_endpoint_count: int = 0


class UpdateIdentitySourceRequest(BaseModel):
    bind_policy: FirstLoginPolicy = Field(default=POLICY_JIT)


class PendingIdentityResponse(BaseModel):
    id: int
    tenant_id: int
    provider_id: int
    provider_display_name: str
    external_subject: str
    email: str | None
    display_name: str | None
    status: IdentityStatus
    created_at: str
