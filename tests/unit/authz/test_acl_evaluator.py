import pytest

from apps.shared.authz.acl import AclCheckInput, AclDecision, evaluate_acl_action
from apps.shared.db.models import AclGrant, ResourceAcl, Tenant, User


@pytest.mark.asyncio
async def test_acl_not_applicable_without_resource_acl(async_db_session):
    tenant = Tenant(name="tenant_acl_na", slug="tenant_acl_na", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="acl_user_na",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)

    decision = await evaluate_acl_action(
        db=async_db_session,
        acl_input=AclCheckInput(
            tenant_id=tenant.id,
            user_id=user.id,
            user_role=user.role,
            resource_type="report",
            resource_id=1001,
            action="read",
        ),
    )

    assert decision == AclDecision.NOT_APPLICABLE


@pytest.mark.asyncio
async def test_acl_owner_fast_path_allows(async_db_session):
    tenant = Tenant(name="tenant_acl_owner", slug="tenant_acl_owner", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    owner = User(
        username="acl_owner",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(owner)
    await async_db_session.commit()
    await async_db_session.refresh(owner)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="report",
            resource_id=2001,
            owner_id=owner.id,
            status="active",
        )
    )
    await async_db_session.commit()

    decision = await evaluate_acl_action(
        db=async_db_session,
        acl_input=AclCheckInput(
            tenant_id=tenant.id,
            user_id=owner.id,
            user_role=owner.role,
            resource_type="report",
            resource_id=2001,
            action="write",
        ),
    )

    assert decision == AclDecision.ALLOW


@pytest.mark.asyncio
async def test_acl_deny_precedence_over_allow(async_db_session):
    tenant = Tenant(name="tenant_acl_deny", slug="tenant_acl_deny", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    user = User(
        username="acl_user_deny",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    owner = User(
        username="acl_owner_deny",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([user, owner])
    await async_db_session.commit()
    await async_db_session.refresh(user)
    await async_db_session.refresh(owner)

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="report",
            resource_id=3001,
            owner_id=owner.id,
            status="active",
        )
    )
    async_db_session.add_all(
        [
            AclGrant(
                tenant_id=tenant.id,
                resource_type="report",
                resource_id=3001,
                principal_type="user",
                principal_id=str(user.id),
                permission="manage",
                effect="allow",
            ),
            AclGrant(
                tenant_id=tenant.id,
                resource_type="report",
                resource_id=3001,
                principal_type="user",
                principal_id=str(user.id),
                permission="write",
                effect="deny",
            ),
        ]
    )
    await async_db_session.commit()

    decision = await evaluate_acl_action(
        db=async_db_session,
        acl_input=AclCheckInput(
            tenant_id=tenant.id,
            user_id=user.id,
            user_role=user.role,
            resource_type="report",
            resource_id=3001,
            action="write",
        ),
    )

    assert decision == AclDecision.DENY
