"""DTOs for tenant module.

Note: TenantDTO and TenantConfigDTO moved to apps.shared.tenant.schemas
Import from there: from apps.shared.tenant.schemas import TenantDTO, TenantConfigDTO
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ModelInfoDTO(BaseModel):
    """Model information from models.yaml registry."""

    key: str = Field(..., description="Model key identifier")
    name: str = Field(..., description="Human-readable model name")
    provider: str = Field(..., description="Model provider (bailian, baidu, etc.)")
    description: str | None = Field(None, description="Model description")


class ModelProviderGroupDTO(BaseModel):
    """Provider-grouped model list for settings UI."""

    provider: str = Field(..., description="Logical provider key")
    models: list[ModelInfoDTO] = Field(default_factory=list, description="Models under this provider")


class StatsResponse(BaseModel):
    """Tenant statistics response model."""

    total_documents: int
    total_assets: int
    total_agents: int
    total_storage_bytes: int


class StorageUsageSnapshot(BaseModel):
    """Current storage usage snapshot for a tenant."""

    total_storage_bytes: int
    document_storage_bytes: int
    database_storage_bytes: int | None = None
    vector_storage_bytes: int | None = None
    updated_at: datetime


class TokenUsageSummary(BaseModel):
    """Token usage summary in a period."""

    period_start: datetime
    period_end: datetime
    total_llm_calls: int
    total_llm_errors: int
    total_tool_calls: int
    total_tool_errors: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    unique_sessions: int
    unique_threads: int
    unique_users: int
    estimated_cost: float | None = None


class TokenUsageDailyPoint(BaseModel):
    """Daily token usage trend point."""

    date: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    llm_calls: int
    llm_errors: int


class TenantUsageSummaryResponse(BaseModel):
    """Combined usage summary response for tenant settings usage tab."""

    storage: StorageUsageSnapshot
    tokens: TokenUsageSummary
    token_daily: list[TokenUsageDailyPoint]


class TokenUsageEventRecord(BaseModel):
    """Single token usage event record."""

    event_id: str
    timestamp: datetime
    session_id: str
    thread_id: str | None = None
    user_id: int | None = None
    username: str | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    model_key: str | None = None
    model_name: str | None = None
    model_label: str | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_ms: float | None = None
    status: str


class TokenUsageEventsResponse(BaseModel):
    """Paginated token usage event response."""

    page: int
    page_size: int
    total: int
    total_pages: int
    rows: list[TokenUsageEventRecord]


class TenantUserDTO(BaseModel):
    """Tenant user response model."""

    id: int
    username: str
    role: Literal["admin", "member", "viewer"]
    tenant_id: int
    tenant_name: str
    membership_status: str
    is_break_glass: bool = False


class TenantUserCreateRequest(BaseModel):
    """Create tenant user request."""

    username: str
    password: str
    role: Literal["admin", "member", "viewer"]
    email: str | None = None


class TenantUserResetPasswordRequest(BaseModel):
    """Reset tenant user password request."""

    new_password: str


class TenantUserUpdateRequest(BaseModel):
    """Update tenant user request."""

    role: Literal["admin", "member", "viewer"]
