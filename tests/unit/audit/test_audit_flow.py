import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.recorder import ACTOR_TYPE_USER, OUTCOME_SUCCESS, TenantAuditRecorder
from apps.shared.audit_event.repository import AuditEventRepository
from apps.shared.db.models import Tenant
from apps.tenant_app_service.audit.service import TenantAuditQueryService


@pytest.mark.asyncio
async def test_write_query_roundtrip(async_db_session: AsyncSession):
    tenant = Tenant(name="t-flow", slug="t-flow", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    recorder = TenantAuditRecorder(async_db_session, tenant_id=tenant.id)
    await recorder.record(
        event_type="user.create",
        outcome=OUTCOME_SUCCESS,
        actor_user_id=99,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id="42",
        payload={"role": "member"},
    )
    await async_db_session.flush()

    service = TenantAuditQueryService(tenant.id, async_db_session)
    page = await service.list_events(page=1, page_size=20)
    assert page.total == 1
    assert page.items[0].event_type == "user.create"
    assert page.items[0].payload == {"role": "member"}

    stats = await service.export_stats()
    assert stats.exported_count == 1
    assert stats.truncated is False