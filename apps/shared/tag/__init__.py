"""Tag system module exports."""

from apps.shared.tag.adapters import domain_resource_tag_config_to_api, domain_tag_key_to_api, domain_tag_value_to_api
from apps.shared.tag.domain import ResourceTagConfigDomain, TagKeyDomain, TagValueDomain
from apps.shared.tag.schemas import (
    ResourceTagConfigCreateRequest,
    ResourceTagConfigDTO,
    ResourceTagConfigUpdateRequest,
    TagBindingCreateRequest,
    TagKeyCreateRequest,
    TagKeyDTO,
    TagKeyUpdateRequest,
    TagValueCreateRequest,
    TagValueDTO,
    TagValueUpdateRequest,
)
from apps.shared.tag.service import TagService

__all__ = [
    "ResourceTagConfigDomain",
    "TagKeyDomain",
    "TagValueDomain",
    "ResourceTagConfigCreateRequest",
    "ResourceTagConfigDTO",
    "ResourceTagConfigUpdateRequest",
    "TagBindingCreateRequest",
    "TagKeyCreateRequest",
    "TagKeyDTO",
    "TagKeyUpdateRequest",
    "TagService",
    "TagValueCreateRequest",
    "TagValueDTO",
    "TagValueUpdateRequest",
    "domain_resource_tag_config_to_api",
    "domain_tag_key_to_api",
    "domain_tag_value_to_api",
]
