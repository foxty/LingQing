"""Schemas for repository-shipped API connector packs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.shared.external_systems.api_connector.constants import (
    AUTH_TYPE_OAUTH2,
    TOKEN_AUTH_METHOD_CLIENT_SECRET_POST,
)
from apps.shared.external_systems.api_connector.domain import TokenAuthMethod
from apps.shared.external_systems.api_connector.schemas import ApiExecutionRulesSchema
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER


class PackConnectorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    base_url: str
    credential_mode: Literal[CREDENTIAL_MODE_USER] = CREDENTIAL_MODE_USER
    auth_type: Literal[AUTH_TYPE_OAUTH2] = AUTH_TYPE_OAUTH2


class PackOAuthSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorize_url: str
    token_url: str
    scopes: list[str] = Field(default_factory=list)
    scope_param: str = "scope"
    token_auth_method: TokenAuthMethod = TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
    token_response_path: str | None = None


class PackOperationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    path: str
    operation_id: str
    summary: str
    description: str | None = None
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]
    enabled: bool = True


class ApiConnectorPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    agent_instructions: str | None = Field(default=None, max_length=8000)
    connector: PackConnectorSchema
    oauth: PackOAuthSchema
    execution_rules: ApiExecutionRulesSchema = Field(default_factory=ApiExecutionRulesSchema)
    operations: list[PackOperationSchema] = Field(..., min_length=1)

    @property
    def pack_ref(self) -> str:
        major = self.version.split(".", maxsplit=1)[0]
        return f"{self.pack_id}@{major}"


class ApiConnectorPackSummary(BaseModel):
    pack_id: str
    version: str
    name: str
    description: str | None = None


class ApiConnectorPackListResponse(BaseModel):
    items: list[ApiConnectorPackSummary]


class InstallApiConnectorPackRequest(BaseModel):
    pack_id: str
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    redirect_uri: str | None = None
