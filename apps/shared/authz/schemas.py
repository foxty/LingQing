"""DTOs for ABAC policies."""

from datetime import datetime

from pydantic import BaseModel

from apps.shared.domain.types import ABAC_ACTION_READ, AbacAction, ResourceType


class AbacPolicyDTO(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None
    resource_type: ResourceType
    action: AbacAction = ABAC_ACTION_READ
    expression: str
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


class AbacPolicyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    resource_type: ResourceType
    action: AbacAction = ABAC_ACTION_READ
    expression: str


class AbacPolicyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    resource_type: ResourceType | None = None
    action: AbacAction | None = None
    expression: str | None = None


class AbacPolicyValidateRequest(BaseModel):
    expression: str


class AbacPolicyValidateResponse(BaseModel):
    valid: bool
    errors: list[str]
    human_readable: str | None


class AbacPolicySimulateRequest(BaseModel):
    expression: str
    resource_type: ResourceType
    action: AbacAction = ABAC_ACTION_READ
    user_id: int
    resource_id: int
    user_role: str | None = None


class AbacPolicySimulateResponse(BaseModel):
    allowed: bool
    reason: str


class AbacPolicySeedResponse(BaseModel):
    created: int
    skipped: int
