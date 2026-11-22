"""Unit tests for tenant membership guard on admin BYOT flows."""

from __future__ import annotations

import pytest

from apps.shared.domain.membership import MembershipStatus, UserAccountStatus
from apps.shared.db.models import Tenant, TenantMembership, User
from apps.shared.tenant.membership_repository import TenantMembershipRepository


@pytest.mark.asyncio
async def test_get_active_member_user_rejects_unknown_user(async_db_session):
    tenant = Tenant(name="t", slug="t", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    repo = TenantMembershipRepository(async_db_session)
    assert await repo.get_active_member_user(tenant_id=tenant.id, user_id=999_999) is None


@pytest.mark.asyncio
async def test_get_active_member_user_accepts_active_membership(async_db_session):
    tenant = Tenant(name="t2", slug="t2", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="member",
        email="m@test.local",
        hashed_password="x",
        tenant_id=tenant.id,
        role="member",
    )
    async_db_session.add(user)
    await async_db_session.flush()
    async_db_session.add(
        TenantMembership(tenant_id=tenant.id, user_id=user.id, status=MembershipStatus.ACTIVE)
    )
    await async_db_session.flush()

    repo = TenantMembershipRepository(async_db_session)
    resolved = await repo.get_active_member_user(tenant_id=tenant.id, user_id=user.id)
    assert resolved is not None
    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_get_active_member_user_rejects_inactive_membership(async_db_session):
    tenant = Tenant(name="t3", slug="t3", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="inactive_m",
        email="inactive_m@test.local",
        hashed_password="x",
        tenant_id=tenant.id,
        role="member",
    )
    async_db_session.add(user)
    await async_db_session.flush()
    async_db_session.add(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            status=MembershipStatus.INACTIVE,
        )
    )
    await async_db_session.flush()

    repo = TenantMembershipRepository(async_db_session)
    assert await repo.get_active_member_user(tenant_id=tenant.id, user_id=user.id) is None


@pytest.mark.asyncio
async def test_get_active_member_user_rejects_inactive_account(async_db_session):
    tenant = Tenant(name="t4", slug="t4", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="disabled",
        email="disabled@test.local",
        hashed_password="x",
        tenant_id=tenant.id,
        role="member",
        status=UserAccountStatus.INACTIVE,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    async_db_session.add(
        TenantMembership(tenant_id=tenant.id, user_id=user.id, status=MembershipStatus.ACTIVE)
    )
    await async_db_session.flush()

    repo = TenantMembershipRepository(async_db_session)
    assert await repo.get_active_member_user(tenant_id=tenant.id, user_id=user.id) is None
