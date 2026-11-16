import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.recorder import TenantAuditRecorder


@pytest.mark.asyncio
async def test_recorder_propagates_persistence_error(async_db_session: AsyncSession, monkeypatch):
    class _BrokenRepo:
        def __init__(self, db):
            self.db = db

        async def add_event(self, **kwargs):
            raise RuntimeError("audit db unavailable")

    monkeypatch.setattr(
        "apps.shared.audit_event.recorder.AuditEventRepository",
        _BrokenRepo,
    )
    recorder = TenantAuditRecorder(async_db_session, tenant_id=1)
    with pytest.raises(RuntimeError, match="audit db unavailable"):
        await recorder.record(
            event_type="test.event",
            outcome="success",
            actor_user_id=1,
            actor_type="user",
            payload={"ok": True},
        )