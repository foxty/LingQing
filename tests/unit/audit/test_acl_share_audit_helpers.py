import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.event_types import TenantAuditEventType
from apps.shared.db.models import AuditEvent, Tenant
from apps.shared.domain.types import RESOURCE_TYPE_AGENT, RESOURCE_TYPE_DOCUMENT_COLLECTION
from apps.shared.audit_event.record_helpers import record_acl_share_create, record_acl_share_revoke


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource_type", "resource_id", "event_type"),
    [
        (RESOURCE_TYPE_DOCUMENT_COLLECTION, 10, TenantAuditEventType.ACL_SHARE_CREATE.value),
        (RESOURCE_TYPE_AGENT, 42, TenantAuditEventType.ACL_SHARE_CREATE.value),
    ],
)
async def test_record_acl_share_create_all_resource_types(
    async_db_session: AsyncSession,
    resource_type: str,
    resource_id: int,
    event_type: str,
):
    tenant = Tenant(name="t-acl-audit", slug="t-acl-audit", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    await record_acl_share_create(
        async_db_session,
        tenant_id=tenant.id,
        actor_user_id=7,
        resource_type=resource_type,
        resource_id=resource_id,
        shared_with_user_id=99,
        permission="read",
    )
    await async_db_session.flush()

    row = (
        await async_db_session.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant.id,
                AuditEvent.event_type == event_type,
            )
        )
    ).scalar_one()
    assert row.resource_type == resource_type
    assert row.resource_id == str(resource_id)
    assert row.payload == {"shared_with_user_id": 99, "permission": "read"}


@pytest.mark.asyncio
async def test_record_acl_share_revoke(async_db_session: AsyncSession):
    tenant = Tenant(name="t-acl-revoke", slug="t-acl-revoke", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    await record_acl_share_revoke(
        async_db_session,
        tenant_id=tenant.id,
        actor_user_id=3,
        resource_type=RESOURCE_TYPE_AGENT,
        resource_id=5,
        shared_with_user_id=8,
    )
    await async_db_session.flush()

    row = (
        await async_db_session.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant.id,
                AuditEvent.event_type == TenantAuditEventType.ACL_SHARE_REVOKE.value,
            )
        )
    ).scalar_one()
    assert row.resource_type == RESOURCE_TYPE_AGENT
    assert row.payload == {"shared_with_user_id": 8}