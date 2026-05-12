"""Pydantic schemas for API connector APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

from apps.shared.api_connector.constants import (
    AUTH_REQUIREMENT_REQUIRED,
    AUTH_TYPE_NONE,
    DEFAULT_HTTP_TIMEOUT_MS,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_MAX_REQUESTS_PER_SECOND,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_MS,
    DEFAULT_RETRY_ON_STATUS,
    RISK_LEVEL_MEDIUM,
)
from apps.shared.api_connector.domain import (
    AuthRequirement,
    AuthType,
    ConnectorStatus,
    OperationSource,
    OperationStatus,
    RatePolicyDomain,
    RiskLevel,
    SchemaSourceType,
)
from apps.shared.schemas.pagination import PaginatedResponse

# Pydantic validation models for API boundary
# These validate incoming requests and convert to domain dataclasses


def _get_auth_method(v: Any) -> str:
    """Extract discriminator field from auth config dict."""
    if isinstance(v, dict):
        return v.get("auth_method", "none")
    return "none"


class ApiKeyAuthConfigSchema(BaseModel):
    """API Key authentication configuration (Pydantic validation)."""

    model_config = ConfigDict(extra="forbid")
    auth_method: Literal["api_key"] = Field(default="api_key")
    key_name: str = Field(default="X-API-Key")
    key_value: str | None = None
    api_key: str | None = None


class BearerAuthConfigSchema(BaseModel):
    """Bearer token authentication configuration (Pydantic validation)."""

    model_config = ConfigDict(extra="forbid")
    auth_method: Literal["bearer"] = Field(default="bearer")
    token: str | None = None
    access_token: str | None = None


class BasicAuthConfigSchema(BaseModel):
    """HTTP Basic authentication configuration (Pydantic validation)."""

    model_config = ConfigDict(extra="forbid")
    auth_method: Literal["basic"] = Field(default="basic")
    username: str | None = None
    password: str | None = None


class NoAuthConfigSchema(BaseModel):
    """No authentication configuration (Pydantic validation)."""

    model_config = ConfigDict(extra="forbid")
    auth_method: Literal["none"] = Field(default="none")


class CustomAuthConfigSchema(BaseModel):
    """Custom/session-based authentication configuration (Pydantic validation)."""

    model_config = ConfigDict(extra="forbid")
    auth_method: Literal["custom"] = Field(default="custom")
    login_endpoint: str = Field(..., description="Path to login endpoint")
    login_method: str = Field(default="POST")
    login_payload_template: dict[str, Any] = Field(default_factory=dict)
    token_extraction: dict[str, str] = Field(default_factory=dict)
    request_headers: dict[str, str] = Field(default_factory=dict)
    extra_config: dict[str, Any] = Field(default_factory=dict)


# Discriminated union for API validation
AuthConfigSchema = Annotated[
    (
        Annotated[NoAuthConfigSchema, Tag("none")]
        | Annotated[ApiKeyAuthConfigSchema, Tag("api_key")]
        | Annotated[BearerAuthConfigSchema, Tag("bearer")]
        | Annotated[BasicAuthConfigSchema, Tag("basic")]
        | Annotated[CustomAuthConfigSchema, Tag("custom")]
    ),
    Discriminator(_get_auth_method),
]


class ApiRatePolicySchema(BaseModel):
    timeout_ms: int = DEFAULT_HTTP_TIMEOUT_MS
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff_ms: int = DEFAULT_RETRY_BACKOFF_MS
    retry_on_status: list[int] = Field(default_factory=lambda: list(DEFAULT_RETRY_ON_STATUS))
    max_requests_per_second: float = DEFAULT_MAX_REQUESTS_PER_SECOND
    burst_size: int | None = None
    max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS

    def to_domain(self) -> RatePolicyDomain:
        return RatePolicyDomain.from_raw(self.model_dump(exclude_none=True))

    @classmethod
    def from_domain(cls, domain: RatePolicyDomain) -> ApiRatePolicySchema:
        return cls(**domain.to_policy_dict())


# API request/response schemas
class ApiConnectorCreateRequest(BaseModel):
    name: str
    description: str | None = None
    base_url: str
    auth_type: AuthType = AUTH_TYPE_NONE
    # Use discriminated union with 'auth_method' field for proper validation and serialization
    auth_config: AuthConfigSchema = Field(default_factory=dict)
    rate_policy: ApiRatePolicySchema = Field(default_factory=ApiRatePolicySchema)
    schema_source_type: SchemaSourceType
    schema_source_url: str | None = None


class ApiConnectorUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    base_url: str | None = None
    auth_type: AuthType | None = None
    # Use discriminated union with 'auth_method' field for proper validation and serialization
    auth_config: AuthConfigSchema | None = None
    rate_policy: ApiRatePolicySchema | None = None
    schema_source_type: SchemaSourceType | None = None
    schema_source_url: str | None = None
    status: ConnectorStatus | None = None


class ApiConnectorResponse(BaseModel):
    id: int
    tenant_id: int
    owner_id: int
    owner_name: str | None = Field(default=None, description="Canonical owner username")
    name: str
    description: str | None
    base_url: str
    auth_type: AuthType
    auth_config_masked: dict[str, Any]
    rate_policy: ApiRatePolicySchema
    schema_source_type: SchemaSourceType
    schema_source_url: str | None
    schema_metadata: dict[str, Any]
    schema_last_synced_at: datetime | None
    status: ConnectorStatus
    created_at: datetime
    updated_at: datetime


class SyncSchemaRequest(BaseModel):
    file_content: str | None = None


class SyncSchemaSummaryDTO(BaseModel):
    added: int
    updated: int
    staled: int
    unchanged: int


class SyncSchemaResponse(BaseModel):
    operations_created: int
    added: int
    updated: int
    staled: int
    unchanged: int


class ApiOperationCreateRequest(BaseModel):
    method: str
    path_template: str
    operation_id: str | None = None
    summary: str = ""
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]
    auth_requirement: AuthRequirement = AUTH_REQUIREMENT_REQUIRED
    risk_level: RiskLevel = RISK_LEVEL_MEDIUM


class ApiOperationUpdateRequest(BaseModel):
    method: str | None = None
    path_template: str | None = None
    operation_id: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    auth_requirement: AuthRequirement | None = None
    risk_level: RiskLevel | None = None


class ApiOperationResponse(BaseModel):
    id: int
    connector_id: int
    operation_uid: str
    method: str
    path_template: str
    operation_id: str | None
    summary: str
    description: str | None
    tags: list[str]
    request_schema: dict[str, Any] | None
    response_schema: dict[str, Any] | None
    auth_requirement: AuthRequirement
    risk_level: RiskLevel
    source: OperationSource
    upstream_key: str | None
    status: OperationStatus
    owner_id: int
    created_at: datetime
    updated_at: datetime
    last_vector_synced_at: datetime | None = None
    last_vector_sync_error: str | None = None
    last_vector_sync_failed_at: datetime | None = None


class ApiOperationStatusUpdateRequest(BaseModel):
    status: OperationStatus


class ApiOperationSearchResponse(PaginatedResponse[ApiOperationResponse]):
    pass


class ApiOperationStatsResponse(BaseModel):
    path_count: int
    total: int
    active: int
    disabled: int
    stale: int
    manual: int
    imported: int


class ApiOperationCallParameters(BaseModel):
    """Typed payload for external API operation runtime arguments.

    Keys:
    - path: path template variables, e.g. {"user_id": 1}
    - query: URL query parameters
    - header: additional request headers
    - body: JSON request body
    """

    path: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    header: dict[str, Any] = Field(default_factory=dict)
    body: Any = None


class ApiOperationCallRequest(BaseModel):
    parameters: ApiOperationCallParameters = Field(default_factory=ApiOperationCallParameters)


class ApiOperationCallResponse(BaseModel):
    status_code: int
    body: Any
    headers: dict[str, str]
    elapsed_ms: float
    error: str | None = None
