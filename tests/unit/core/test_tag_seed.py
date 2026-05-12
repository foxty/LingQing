"""Unit tests for default tag seeding."""

import pytest
from sqlalchemy import func, select

from apps.shared.core.tag_seed import DEFAULT_RESOURCE_TAG_CONFIGS, DEFAULT_TAG_KEYS, seed_default_tags
from apps.shared.db.models import ResourceTagConfig, TagKey, TagValue, Tenant


@pytest.mark.asyncio
async def test_seed_default_tags_creates_keys_values_and_resource_configs(async_db_session):
    tenant = Tenant(name="tenant_tag_seed", slug="tenant_tag_seed", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    await seed_default_tags(async_db_session, tenant.id)
    await async_db_session.commit()

    key_rows = await async_db_session.execute(select(TagKey).where(TagKey.tenant_id == tenant.id))
    keys = list(key_rows.scalars().all())
    assert len(keys) == len(DEFAULT_TAG_KEYS)
    assert all(key.status == "active" for key in keys)

    value_rows = await async_db_session.execute(select(TagValue).where(TagValue.tenant_id == tenant.id))
    values = list(value_rows.scalars().all())
    expected_value_count = sum(len(item["values"]) for item in DEFAULT_TAG_KEYS)
    assert len(values) == expected_value_count
    assert all(value.status == "active" for value in values)

    key_name_by_id = {key.id: key.name for key in keys}
    security_values = {value.value: value.rank for value in values if key_name_by_id[value.key_id] == "数据安全性"}
    assert security_values == {
        "公开": 1,
        "内部": 2,
        "敏感": 3,
        "机密": 4,
    }

    config_rows = await async_db_session.execute(
        select(ResourceTagConfig).where(ResourceTagConfig.tenant_id == tenant.id)
    )
    configs = list(config_rows.scalars().all())
    expected_config_count = sum(len(items) for items in DEFAULT_RESOURCE_TAG_CONFIGS.values())
    assert len(configs) == expected_config_count

    expected_modes = {
        (resource_type, item["key_name"]): item["value_mode"]
        for resource_type, items in DEFAULT_RESOURCE_TAG_CONFIGS.items()
        for item in items
    }

    for config in configs:
        key_name = key_name_by_id[config.tag_key_id]
        assert config.value_mode == expected_modes[(config.resource_type, key_name)]


@pytest.mark.asyncio
async def test_seed_default_tags_is_idempotent(async_db_session):
    tenant = Tenant(name="tenant_tag_seed_idempotent", slug="tenant_tag_seed_idempotent", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    await seed_default_tags(async_db_session, tenant.id)
    await async_db_session.commit()

    await seed_default_tags(async_db_session, tenant.id)
    await async_db_session.commit()

    key_count = await async_db_session.scalar(select(func.count(TagKey.id)).where(TagKey.tenant_id == tenant.id))
    value_count = await async_db_session.scalar(select(func.count(TagValue.id)).where(TagValue.tenant_id == tenant.id))
    config_count = await async_db_session.scalar(
        select(func.count(ResourceTagConfig.id)).where(ResourceTagConfig.tenant_id == tenant.id)
    )

    assert key_count == len(DEFAULT_TAG_KEYS)
    assert value_count == sum(len(item["values"]) for item in DEFAULT_TAG_KEYS)
    assert config_count == sum(len(items) for items in DEFAULT_RESOURCE_TAG_CONFIGS.values())
