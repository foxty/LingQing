"""Pydantic schemas for tenant manager P0 APIs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.shared.schemas.principal import TenantManagerPrincipal


class TenantCreateRequest(BaseModel):
    """Create tenant request."""

    tenant_code: str = Field(min_length=2, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)


class TenantResponse(BaseModel):
    """Tenant response schema."""

    model_config = ConfigDict(from_attributes=True)

    tenant_uid: str
    tenant_code: str
    display_name: str
    status: str
    created_at: datetime
    updated_at: datetime


class TenantStatusActionRequest(BaseModel):
    """Status transition action request."""

    reason_code: str | None = Field(default=None, max_length=50)


class TenantLifecycleEventResponse(BaseModel):
    """Lifecycle event response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_uid: str
    event_type: str
    from_status: str | None
    to_status: str
    reason_code: str | None
    operator_id: str | None
    event_metadata: dict | None
    created_at: datetime


class TenantListResponse(BaseModel):
    """List response wrapper."""

    items: list[TenantResponse]


class TMLoginRequest(BaseModel):
    """Local login request for tenant manager."""

    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class TMUserCreateRequest(BaseModel):
    """Create local control-plane user."""

    username: str = Field(min_length=2, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(min_length=1, max_length=50)


class TMBootstrapAdminRequest(BaseModel):
    """Bootstrap first platform admin when user table is empty."""

    username: str = Field(min_length=2, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class TMUserUpdateStatusRequest(BaseModel):
    """Update local user status request."""

    status: str = Field(min_length=1, max_length=20)


class TMUserResponse(BaseModel):
    """Tenant manager local user response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class TMUserListResponse(BaseModel):
    """List response for TM users."""

    items: list[TMUserResponse]


class TMLoginResponse(BaseModel):
    """Tenant manager login response."""

    access_token: str
    token_type: str
    user: TMUserResponse


class TMPrincipal(TenantManagerPrincipal):
    """Control-plane principal extracted from JWT."""
