"""Unit tests for live app ORM model."""

import pytest
from sqlalchemy.exc import IntegrityError

from apps.shared.db.models import DataSource, LiveApp, Tenant, User


@pytest.mark.asyncio
async def test_live_app_defaults(async_db_session):
    tenant = Tenant(name="tenant_live_app_defaults", slug="tenant_live_app_defaults", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="live_app_owner",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    data_source = DataSource(
        tenant_id=tenant.id,
        owner_id=user.id,
        name="analytics_main",
        type="postgres",
        managed=True,
        config={},
    )
    async_db_session.add(data_source)
    await async_db_session.flush()

    live_app = LiveApp(
        tenant_id=tenant.id,
        owner_id=user.id,
        data_source_id=data_source.id,
        name="commission_app",
    )
    async_db_session.add(live_app)
    await async_db_session.commit()
    await async_db_session.refresh(live_app)

    assert live_app.entry_file == "entry.html"
    assert live_app.app_config == {}
    assert live_app.sdk_version == "1.0"
    assert live_app.status == "draft"


@pytest.mark.asyncio
async def test_live_app_name_unique_within_tenant(async_db_session):
    tenant = Tenant(name="tenant_live_app_unique", slug="tenant_live_app_unique", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="live_app_unique_owner", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    first = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="same_name")
    second = LiveApp(tenant_id=tenant.id, owner_id=user.id, name="same_name")
    async_db_session.add(first)
    await async_db_session.flush()
    async_db_session.add(second)

    with pytest.raises(IntegrityError):
        await async_db_session.commit()
