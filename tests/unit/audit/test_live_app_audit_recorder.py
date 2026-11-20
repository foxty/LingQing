import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AuditEvent, Tenant
from apps.shared.live_app.domain import LiveAppAuditEventType
from apps.shared.live_app.service import LiveAppService


@pytest.mark.asyncio
async def test_live_app_record_audit_event_uses_tenant_recorder(async_db_session: AsyncSession):
    tenant = Tenant(name="t-live-audit", slug="t-live-audit", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)
    await service._record_audit_event(
        actor_user_id=42,
        event_type=LiveAppAuditEventType.DATA_QUERY,
        payload={"app_id": 7, "row_count": 3, "token": "secret-should-drop"},
    )
    await async_db_session.flush()

    row = (
        await async_db_session.execute(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant.id,
                AuditEvent.event_type == LiveAppAuditEventType.DATA_QUERY.value,
            )
        )
    ).scalar_one()
    assert row.actor_user_id == 42
    assert row.resource_type == "live_app"
    assert row.resource_id == "7"
    assert row.payload == {"app_id": 7, "row_count": 3}
    assert "token" not in (row.payload or {})


@pytest.mark.asyncio
async def test_live_app_audit_recorder_fail_closed_propagates(monkeypatch, async_db_session: AsyncSession):
    class _BrokenRecorder:
        def __init__(self, *args, **kwargs):
            pass

        async def record(self, **kwargs):
            raise RuntimeError("audit unavailable")

    monkeypatch.setattr(
        "apps.shared.audit_event.recorder.TenantAuditRecorder",
        _BrokenRecorder,
    )
    tenant = Tenant(name="t-live-audit-fc", slug="t-live-audit-fc", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()
    service = LiveAppService.create(tenant_id=tenant.id, db_session=async_db_session)

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service._record_audit_event(
            actor_user_id=1,
            event_type=LiveAppAuditEventType.FILE_WRITE,
            payload={"app_id": 1, "path": "x"},
        )