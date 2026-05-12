"""DTOs for tag system."""

from datetime import datetime

from pydantic import BaseModel

from apps.shared.domain.types import ResourceType
from apps.shared.tag.types import TagValueMode


class TagKeyDTO(BaseModel):
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


class TagKeyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None


class TagKeyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class TagValueDTO(BaseModel):
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


class TagValueCreateRequest(BaseModel):
    key_id: int
    value: str
    rank: int | None = None


class TagValueUpdateRequest(BaseModel):
    value: str | None = None
    rank: int | None = None


class ResourceTagConfigDTO(BaseModel):
    id: int
    tenant_id: int
    resource_type: ResourceType
    tag_key_id: int
    value_mode: TagValueMode
    created_at: datetime
    created_by: int | None


class ResourceTagConfigCreateRequest(BaseModel):
    resource_type: ResourceType
    tag_key_id: int
    value_mode: TagValueMode


class ResourceTagConfigUpdateRequest(BaseModel):
    value_mode: TagValueMode


class TagBindingCreateRequest(BaseModel):
    tag_value_id: int
