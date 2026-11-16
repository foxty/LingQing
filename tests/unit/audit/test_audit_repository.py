import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.repository import EXPORT_MAX_ROWS, AuditEventRepository
from apps.shared.db.models import AuditEvent, Tenant


@pytest.mark.asyncio
async def test_list_for_export_truncates(async_db_session: AsyncSession):
    tenant = Tenant(name="t-audit", slug="t-audit", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    repo = AuditEventRepository(async_db_session)
    for i in range(EXPORT_MAX_ROWS + 5):
        async_db_session.add(
            AuditEvent(
                tenant_id=tenant.id,
                actor_user_id=None,
                event_type="test.event",
                payload={"i": i},
            )
        )
    await async_db_session.flush()

    rows, total, truncated = await repo.list_for_export(tenant_id=tenant.id)
    assert total == EXPORT_MAX_ROWS + 5
    assert truncated is True
    assert len(rows) == EXPORT_MAX_ROWS


@pytest.mark.asyncio
async def test_tenant_isolation_on_list(async_db_session: AsyncSession):
    t1 = Tenant(name="t-one", slug="t-one", status="active")
    t2 = Tenant(name="t-two", slug="t-two", status="active")
    async_db_session.add_all([t1, t2])
    await async_db_session.flush()

    repo = AuditEventRepository(async_db_session)
    async_db_session.add(
        AuditEvent(tenant_id=t1.id, event_type="alpha", payload={}),
    )
    async_db_session.add(
        AuditEvent(tenant_id=t2.id, event_type="beta", payload={}),
    )
    await async_db_session.flush()

    rows, total = await repo.list_paginated(tenant_id=t1.id, page=1, page_size=20)
    assert total == 1
    assert rows[0].event_type == "alpha"