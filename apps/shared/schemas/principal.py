"""Shared principal models for authentication contexts."""

from pydantic import BaseModel, model_validator


class BasePrincipal(BaseModel):
    """Minimal principal contract shared by app and control plane."""

    role: str
    sub: str | None = None
    user_id: int | None = None
    provider: str | None = None


class TenantAppPrincipal(BasePrincipal):
    """Principal shape for tenant app requests."""

    tenant_id: int
    tenant_name: str


class TenantManagerPrincipal(BasePrincipal):
    """Principal shape for tenant manager requests."""

    sub: str
    user_id: int
    provider: str


class BackwardCompatibleUserPrincipal(TenantAppPrincipal):
    """Tenant app principal with legacy user DTO fields."""

    id: int
    username: str

    @model_validator(mode="after")
    def fill_principal_defaults(self):
        if self.sub is None:
            self.sub = self.username
        if self.user_id is None:
            self.user_id = self.id
        if self.provider is None:
            self.provider = "native"
        return self
