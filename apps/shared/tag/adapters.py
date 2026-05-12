"""Adapters for tag system."""

from apps.shared.db.models import ResourceTagConfig, TagKey, TagValue
from apps.shared.tag.domain import ResourceTagConfigDomain, TagKeyDomain, TagValueDomain
from apps.shared.tag.schemas import ResourceTagConfigDTO, TagKeyDTO, TagValueDTO


def db_tag_key_to_domain(tag_key: TagKey) -> TagKeyDomain:
    return TagKeyDomain(
        id=tag_key.id,
        tenant_id=tag_key.tenant_id,
        name=tag_key.name,
        description=tag_key.description,
        color=tag_key.color,
        status=tag_key.status,
        created_at=tag_key.created_at,
        updated_at=tag_key.updated_at,
        created_by=tag_key.created_by,
        updated_by=tag_key.updated_by,
    )


def db_tag_value_to_domain(tag_value: TagValue) -> TagValueDomain:
    return TagValueDomain(
        id=tag_value.id,
        tenant_id=tag_value.tenant_id,
        key_id=tag_value.key_id,
        value=tag_value.value,
        rank=tag_value.rank,
        status=tag_value.status,
        created_at=tag_value.created_at,
        updated_at=tag_value.updated_at,
        created_by=tag_value.created_by,
        updated_by=tag_value.updated_by,
    )


def db_resource_tag_config_to_domain(resource_tag: ResourceTagConfig) -> ResourceTagConfigDomain:
    return ResourceTagConfigDomain(
        id=resource_tag.id,
        tenant_id=resource_tag.tenant_id,
        resource_type=resource_tag.resource_type,
        tag_key_id=resource_tag.tag_key_id,
        value_mode=resource_tag.value_mode,
        created_at=resource_tag.created_at,
        created_by=resource_tag.created_by,
    )


def domain_tag_key_to_api(tag_key: TagKeyDomain) -> TagKeyDTO:
    return TagKeyDTO(**tag_key.model_dump())


def domain_tag_value_to_api(tag_value: TagValueDomain) -> TagValueDTO:
    return TagValueDTO(**tag_value.model_dump())


def domain_resource_tag_config_to_api(resource_tag: ResourceTagConfigDomain) -> ResourceTagConfigDTO:
    return ResourceTagConfigDTO(**resource_tag.model_dump())
