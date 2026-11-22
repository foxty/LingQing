"""DTOs for user integration credential APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from apps.shared.external_systems.domain.types import (
    UserConnectionStatus,
)
from apps.shared.schemas.masked_fields import MaskedFieldsMixin


class UserIntegrationConnectionResponse(MaskedFieldsMixin):
    resource_type: str
    resource_id: int
    status: UserConnectionStatus = Field(description="not_connected | connected | expired")
    account_label: str | None = None
    auth_type: str | None = None
    expires_at: datetime | None = None
    secrets: dict[str, str] = Field(
        default_factory=dict,
        description="Redacted secret blob; sensitive leaves show partial mask or are omitted",
    )


class UserIntegrationConnectionUpsertRequest(BaseModel):
    auth_type: str = Field(
        ...,
        description=(
            "Data source: db_password (RDBMS) or pat (Databricks). "
            "API connector: must match connector auth_type (api_key, bearer, basic)."
        ),
    )
    secrets: dict[str, str] = Field(..., description="Plaintext secrets; encrypted server-side")
    account_label: str | None = None


class UserIntegrationConnectionTestResponse(BaseModel):
    success: bool
    message: str


class UserIntegrationConnectionSummary(BaseModel):
    user_id: int
    username: str | None = None
    resource_type: str
    resource_id: int
    resource_name: str | None = None
    status: UserConnectionStatus
    account_label: str | None = None
    auth_type: str | None = None
    updated_at: datetime | None = None
    provisioned_by_user_id: int | None = None
    provisioned_by_username: str | None = None
    provisioned_at: datetime | None = None


class UserIntegrationConnectionSummaryListResponse(BaseModel):
    items: list[UserIntegrationConnectionSummary]
