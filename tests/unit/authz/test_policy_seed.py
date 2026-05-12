"""Unit tests for seed_default_policies."""

import pytest

from apps.shared.core.policy_seed import DEFAULT_ABAC_POLICIES, seed_default_policies
from apps.shared.db.models import AbacPolicy, Tenant


@pytest.mark.asyncio
async def test_seed_creates_default_policies(async_db_session):
    tenant = Tenant(name="seed_test", slug="seed_test", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    result = await seed_default_policies(async_db_session, tenant.id)

    assert result["created"] == len(DEFAULT_ABAC_POLICIES)
    assert result["skipped"] == 0
    await async_db_session.commit()


@pytest.mark.asyncio
async def test_seed_idempotent(async_db_session):
    tenant = Tenant(name="seed_idempotent", slug="seed_idempotent", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    first = await seed_default_policies(async_db_session, tenant.id)
    await async_db_session.commit()

    second = await seed_default_policies(async_db_session, tenant.id)
    await async_db_session.commit()

    assert first["created"] == len(DEFAULT_ABAC_POLICIES)
    assert second["created"] == 0
    assert second["skipped"] == len(DEFAULT_ABAC_POLICIES)


@pytest.mark.asyncio
async def test_seed_partial_idempotent(async_db_session):
    tenant = Tenant(name="seed_partial", slug="seed_partial", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    # Pre-create one policy with a matching name
    first_def = DEFAULT_ABAC_POLICIES[0]
    policy = AbacPolicy(
        id=1,
        tenant_id=tenant.id,
        name=first_def["name"],
        description=first_def["description"],
        resource_type=first_def["resource_type"],
        expression=first_def["expression"],
        status="active",
    )
    async_db_session.add(policy)
    await async_db_session.commit()

    result = await seed_default_policies(async_db_session, tenant.id)
    await async_db_session.commit()

    assert result["created"] == len(DEFAULT_ABAC_POLICIES) - 1
    assert result["skipped"] == 1
