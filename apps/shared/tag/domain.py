"""Domain models for tag system."""

from dataclasses import dataclass
from datetime import datetime

from apps.shared.domain.base_domain_model import BaseDomainModel
from apps.shared.domain.types import ResourceType
from apps.shared.tag.types import TagValueMode


@dataclass
class TagKeyDomain(BaseDomainModel):
    id: int
    tenant_id: int
    name: str
    description: str | None
    color: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


@dataclass
class TagValueDomain(BaseDomainModel):
    id: int
    tenant_id: int
    key_id: int
    value: str
    rank: int | None
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


@dataclass
class ResourceTagConfigDomain(BaseDomainModel):
    id: int
    tenant_id: int
    resource_type: ResourceType
    tag_key_id: int
    value_mode: TagValueMode
    created_at: datetime
    created_by: int | None
