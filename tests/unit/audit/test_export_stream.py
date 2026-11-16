from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import Tenant
from apps.tenant_app_service.audit.service import AuditExportStats, UTF8_BOM, iter_audit_export_csv


@pytest.mark.asyncio
async def test_iter_audit_export_csv_leading_bom(async_db_session: AsyncSession, monkeypatch):
    tenant = Tenant(name="bom-tenant", slug="bom-tenant", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    @asynccontextmanager
    async def _use_test_session():
        yield async_db_session

    monkeypatch.setattr("apps.tenant_app_service.audit.service.app_db_session", _use_test_session)

    stats = AuditExportStats(truncated=False, total_matched=0, exported_count=0)
    agen = iter_audit_export_csv(tenant.id, stats=stats, actor_context_user_id=None)
    first = await agen.__anext__()
    assert first == UTF8_BOM.encode("utf-8")

    # Drain without requiring export self-audit
    async for _ in agen:
        pass