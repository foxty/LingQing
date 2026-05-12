import pytest
from fastapi import HTTPException

from apps.shared.authz.permissions import Permissions
from apps.shared.authz.rbac import get_effective_rbac, role_has_permission
from apps.shared.core.auth import require_permission
from apps.shared.db.models import Tenant
from apps.shared.schemas.user import UserDTO


@pytest.mark.asyncio
async def test_role_has_permission_defaults(async_db_session):
    tenant = Tenant(name="tenant_default", slug="tenant_default", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="admin",
        permission=Permissions.DASHBOARDS_SQL_EXECUTE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="viewer",
        permission=Permissions.DASHBOARDS_SQL_EXECUTE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.DATA_SOURCES_WRITE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.DASHBOARDS_SQL_EXECUTE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.CHAT_ACCESS,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.APPS_WRITE,
    )
    assert not await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="viewer",
        permission=Permissions.APPS_WRITE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="admin",
        permission=Permissions.ARTIFACTS_MANAGE,
    )
    assert not await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.ARTIFACTS_MANAGE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.REPORTS_WRITE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.SCHEDULED_TASKS_WRITE,
    )
    assert not await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="viewer",
        permission=Permissions.REPORTS_WRITE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.DOCUMENTS_READ,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.DOCUMENTS_WRITE,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="member",
        permission=Permissions.DOCUMENTS_READ,
    )
    assert await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="viewer",
        permission=Permissions.DATA_SOURCES_READ,
    )
    assert not await role_has_permission(
        db=async_db_session,
        tenant_id=tenant.id,
        role_key="viewer",
        permission=Permissions.CHAT_ACCESS,
    )


@pytest.mark.asyncio
async def test_get_effective_rbac_defaults(async_db_session):
    tenant = Tenant(name="tenant_rbac", slug="tenant_rbac", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    effective = await get_effective_rbac(db=async_db_session, tenant_id=tenant.id)

    assert effective.default_role_key == "viewer"
    assert set(effective.roles.keys()) >= {"admin", "member", "viewer"}
    assert Permissions.TENANT_ADMIN in effective.roles["admin"]


@pytest.mark.asyncio
async def test_require_permission_denies(async_db_session):
    tenant = Tenant(name="tenant_authz", slug="tenant_authz", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    checker = require_permission(Permissions.CHAT_ACCESS)
    current_user = UserDTO(
        id=1,
        username="viewer",
        role="viewer",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=current_user, db=async_db_session)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_allows(async_db_session):
    tenant = Tenant(name="tenant_authz_admin", slug="tenant_authz_admin", config=None)
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    checker = require_permission(Permissions.DASHBOARDS_SQL_EXECUTE)
    current_user = UserDTO(
        id=1,
        username="admin",
        role="admin",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )

    result = await checker(current_user=current_user, db=async_db_session)
    assert result == current_user
