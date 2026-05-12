"""Unit tests for SSO login access guards."""

import pytest

from apps.shared.auth.membership_access import MembershipStatus, UserAccountStatus
from apps.shared.db.models import Tenant, TenantMembership, User
from apps.tenant_app_service.sso.login_service import SsoLoginService

pytestmark = pytest.mark.asyncio


async def _make_tenant(db, name: str) -> Tenant:
    tenant = Tenant(name=name, slug=name.lower(), status="active")
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def _make_user(
    db,
    tenant_id: int,
    username: str,
    *,
    membership_status: str = MembershipStatus.ACTIVE,
    account_status: str = UserAccountStatus.ACTIVE,
) -> User:
    user = User(
        username=username,
        hashed_password="x",
        role="member",
        tenant_id=tenant_id,
        status=account_status,
    )
    db.add(user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            status=membership_status,
        )
    )
    await db.flush()
    await db.refresh(user)
    return user


async def test_issue_login_ticket_denies_inactive_membership(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    user = await _make_user(
        async_db_session,
        tenant.id,
        "inactive-user",
        membership_status=MembershipStatus.INACTIVE,
    )
    service = SsoLoginService(async_db_session)

    result = await service._issue_login_ticket(tenant_id=tenant.id, user_id=user.id)

    assert result.status == "denied"
    assert result.reason == "membership_inactive"


async def test_issue_login_ticket_denies_disabled_account(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    user = await _make_user(
        async_db_session,
        tenant.id,
        "disabled-user",
        account_status=UserAccountStatus.INACTIVE,
    )
    service = SsoLoginService(async_db_session)

    result = await service._issue_login_ticket(tenant_id=tenant.id, user_id=user.id)

    assert result.status == "denied"
    assert result.reason == "account_disabled"


async def test_issue_login_ticket_allows_active_member(async_db_session):
    tenant = await _make_tenant(async_db_session, "Acme")
    user = await _make_user(async_db_session, tenant.id, "active-user")
    service = SsoLoginService(async_db_session)

    result = await service._issue_login_ticket(tenant_id=tenant.id, user_id=user.id)

    assert result.status == "success"
    assert result.ticket
    assert result.user_id == user.id
