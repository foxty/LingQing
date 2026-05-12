"""Default tag seed definitions and helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ResourceTagConfig, TagKey, TagValue
from apps.shared.tag.repository import (
    ResourceTagConfigRepository,
    TagKeyRepository,
    TagValueRepository,
)

DEFAULT_TAG_KEYS = [
    {
        "name": "部门",
        "color": "#2563eb",
        "values": [
            {"value": "研发", "rank": None},
            {"value": "产品", "rank": None},
            {"value": "运营", "rank": None},
            {"value": "销售", "rank": None},
            {"value": "财务", "rank": None},
            {"value": "人事", "rank": None},
            {"value": "法务", "rank": None},
            {"value": "管理", "rank": None},
        ],
    },
    {
        "name": "数据安全性",
        "color": "#dc2626",
        "values": [
            {"value": "公开", "rank": 1},
            {"value": "内部", "rank": 2},
            {"value": "敏感", "rank": 3},
            {"value": "机密", "rank": 4},
        ],
    },
    {
        "name": "地区",
        "color": "#0f766e",
        "values": [
            {"value": "华北", "rank": None},
            {"value": "华东", "rank": None},
            {"value": "华南", "rank": None},
            {"value": "海外", "rank": None},
        ],
    },
]

DEFAULT_RESOURCE_TAG_CONFIGS = {
    "document": [
        {"key_name": "部门", "value_mode": "exclusive"},
        {"key_name": "数据安全性", "value_mode": "exclusive"},
        {"key_name": "地区", "value_mode": "inclusive"},
    ],
    "asset": [
        {"key_name": "部门", "value_mode": "exclusive"},
        {"key_name": "数据安全性", "value_mode": "exclusive"},
        {"key_name": "地区", "value_mode": "inclusive"},
    ],
    "user": [
        {"key_name": "部门", "value_mode": "exclusive"},
        {"key_name": "数据安全性", "value_mode": "exclusive"},
        {"key_name": "地区", "value_mode": "inclusive"},
    ],
}


async def seed_default_tags(db: AsyncSession, tenant_id: int) -> None:
    """Seed default tag keys/values and whitelist for a tenant.

    This is intended to run during tenant provisioning.
    """
    tag_key_repo = TagKeyRepository(db)
    tag_value_repo = TagValueRepository(db)
    resource_tag_repo = ResourceTagConfigRepository(db)

    if await tag_key_repo.has_any_for_tenant(tenant_id):
        return

    is_sqlite = bool(db.bind and db.bind.dialect.name == "sqlite")
    next_tag_key_id: int | None = None
    next_tag_value_id: int | None = None
    next_resource_tag_config_id: int | None = None
    if is_sqlite:
        max_tag_key_id = await db.scalar(select(func.max(TagKey.id)))
        max_tag_value_id = await db.scalar(select(func.max(TagValue.id)))
        max_resource_tag_config_id = await db.scalar(select(func.max(ResourceTagConfig.id)))
        next_tag_key_id = int(max_tag_key_id or 0) + 1
        next_tag_value_id = int(max_tag_value_id or 0) + 1
        next_resource_tag_config_id = int(max_resource_tag_config_id or 0) + 1

    tag_keys: list[TagKey] = []
    for key in DEFAULT_TAG_KEYS:
        key_kwargs = {
            "tenant_id": tenant_id,
            "name": key["name"],
            "description": None,
            "color": key.get("color"),
            "status": "active",
        }
        if next_tag_key_id is not None:
            key_kwargs["id"] = next_tag_key_id
            next_tag_key_id += 1
        tag_keys.append(TagKey(**key_kwargs))
    await tag_key_repo.create_many(tag_keys)

    key_id_by_name = {key.name: key.id for key in tag_keys}

    tag_values: list[TagValue] = []
    for key in DEFAULT_TAG_KEYS:
        if key["name"] not in key_id_by_name:
            continue
        for item in key["values"]:
            value_kwargs = {
                "tenant_id": tenant_id,
                "key_id": key_id_by_name[key["name"]],
                "value": item["value"],
                "rank": item.get("rank"),
                "status": "active",
            }
            if next_tag_value_id is not None:
                value_kwargs["id"] = next_tag_value_id
                next_tag_value_id += 1
            tag_values.append(TagValue(**value_kwargs))
    await tag_value_repo.create_many(tag_values)

    resource_tag_configs: list[ResourceTagConfig] = []
    for resource_type, config_items in DEFAULT_RESOURCE_TAG_CONFIGS.items():
        for config_item in config_items:
            if config_item["key_name"] not in key_id_by_name:
                continue
            config_kwargs = {
                "tenant_id": tenant_id,
                "resource_type": resource_type,
                "tag_key_id": key_id_by_name[config_item["key_name"]],
                "value_mode": config_item["value_mode"],
            }
            if next_resource_tag_config_id is not None:
                config_kwargs["id"] = next_resource_tag_config_id
                next_resource_tag_config_id += 1
            resource_tag_configs.append(ResourceTagConfig(**config_kwargs))
    await resource_tag_repo.create_many(resource_tag_configs)
