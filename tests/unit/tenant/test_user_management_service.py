"""Unit tests for tenant user deactivate invariants."""

import uuid

import pytest
from sqlalchemy import select

from apps.shared.core.exceptions import ValidationError
from apps.shared.db.models import Tenant, TenantMembership, User
from apps.tenant_app_service.auth.domain import MembershipStatus, UserRole
from apps.tenant_app_service.tenant.user_management_service import TenantUserManagementService

pytestmark = pytest.mark.asyncio


async def _make_tenant(db, name: str) -> Tenant:
    slug = f"{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}"
    tenant = Tenant(name=name, slug=slug, status="active")
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def _make_user(db, tenant_id: int, username: str, role: str = UserRole.MEMBER) -> User:
    user = User(
        username=username,
        hashed_password="x",
        role=role,
        tenant_id=tenant_id,
        status="active",
    )
    db.add(user)
    await db.flush()
    membership = TenantMembership(
        tenant_id=tenant_id,
        user_id=user.id,
        status=MembershipStatus.ACTIVE,
    )
    db.add(membership)
    await db.flush()
    await db.refresh(user)
    return user


async def test_cannot_deactivate_self(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    admin = await _make_user(async_db_session, tenant.id, "admin", role=UserRole.ADMIN)
    other = await _make_user(async_db_session, tenant.id, "other", role=UserRole.ADMIN)
    service = TenantUserManagementService(tenant_id=tenant.id, db=async_db_session)

    with pytest.raises(ValidationError, match="Cannot deactivate your own account"):
        await service.deactivate_user(user_id=admin.id, actor_user_id=admin.id)

    await service.deactivate_user(user_id=other.id, actor_user_id=admin.id)

    result = await async_db_session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == other.id,
        )
    )
    assert result.scalar_one().status == MembershipStatus.INACTIVE


async def test_cannot_deactivate_last_active_admin(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    admin = await _make_user(async_db_session, tenant.id, "admin", role=UserRole.ADMIN)
    member = await _make_user(async_db_session, tenant.id, "member", role=UserRole.MEMBER)
    service = TenantUserManagementService(tenant_id=tenant.id, db=async_db_session)

    with pytest.raises(ValidationError, match="Tenant must have at least one admin"):
        await service.deactivate_user(user_id=admin.id, actor_user_id=member.id)


async def test_can_deactivate_non_admin_when_one_admin_remains(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    admin = await _make_user(async_db_session, tenant.id, "admin", role=UserRole.ADMIN)
    member = await _make_user(async_db_session, tenant.id, "member", role=UserRole.MEMBER)
    service = TenantUserManagementService(tenant_id=tenant.id, db=async_db_session)

    await service.deactivate_user(user_id=member.id, actor_user_id=admin.id)

    result = await async_db_session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == member.id,
        )
    )
    assert result.scalar_one().status == MembershipStatus.INACTIVE


async def test_list_users_pagination_and_search(async_db_session):
    tenant = await _make_tenant(async_db_session, "PaginateCo")
    other_tenant = await _make_tenant(async_db_session, "OtherCo")
    u_alice = await _make_user(async_db_session, tenant.id, "alice", role=UserRole.MEMBER)
    u_bob = await _make_user(async_db_session, tenant.id, "bob", role=UserRole.ADMIN)
    u_carol = await _make_user(async_db_session, tenant.id, "carol", role=UserRole.ADMIN)
    await _make_user(async_db_session, other_tenant.id, "dave", role=UserRole.MEMBER)

    service = TenantUserManagementService(tenant_id=tenant.id, db=async_db_session)

    page1 = await service.list_users(page=1, page_size=2, query=None)
    assert page1.total == 3
    assert page1.total_tenant_members == 3
    assert page1.active_admin_count == 2
    assert page1.total_pages == 2
    assert len(page1.items) == 2
    assert page1.items[0].id == u_alice.id
    assert page1.items[1].id == u_bob.id

    page2 = await service.list_users(page=2, page_size=2, query=None)
    assert page2.total == 3
    assert len(page2.items) == 1
    assert page2.items[0].id == u_carol.id

    search_alice = await service.list_users(page=1, page_size=10, query="Ali")
    assert search_alice.total == 1
    assert search_alice.items[0].username == "alice"

    search_id = await service.list_users(page=1, page_size=10, query=str(u_bob.id))
    assert search_id.total == 1
    assert search_id.items[0].id == u_bob.id
