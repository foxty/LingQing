"""Domain models for ABAC policies."""

from dataclasses import dataclass
from datetime import datetime

from apps.shared.domain.base_domain_model import BaseDomainModel
from apps.shared.domain.types import AbacAction, ResourceType


@dataclass
class AbacPolicyDomain(BaseDomainModel):
    # NOTE: `resource_type` scopes where this policy can be evaluated (e.g., dataset,
    # dashboard). It is metadata for routing/validation, not an expression clause.
    # The `expression` is a raw DSL string evaluated against a predefined
    # attribute context (e.g., :user.id, :user.tags, :resource.tags).
    # Example:
    # :user.tags has "department:engineering" and :user.tags contains :resource.tags
    id: int
    tenant_id: int
    name: str
    description: str | None
    resource_type: ResourceType
    action: AbacAction
    expression: str
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None
