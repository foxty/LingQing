"""DTOs for user integration credential APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from apps.shared.external_systems.domain.types import (
    UserConnectionStatus,
)


class UserIntegrationConnectionResponse(BaseModel):
    resource_type: str
    resource_id: int
    status: UserConnectionStatus = Field(description="not_connected | connected | expired")
    account_label: str | None = None
    auth_type: str | None = None
    expires_at: datetime | None = None
    secrets_public: dict[str, str] = Field(
        default_factory=dict,
        description="Non-sensitive saved secret fields (e.g. username) for edit forms",
    )
    secret_keys_configured: list[str] = Field(
        default_factory=list,
        description="Sensitive secret keys that have a saved value",
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
