from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AuditEvent, Tenant
from apps.tenant_app_service.audit.service import (
    AUDIT_EXPORT_HEADERS,
    AuditExportStats,
    UTF8_BOM,
    iter_audit_export_csv,
)


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


@pytest.mark.asyncio
async def test_export_csv_includes_user_agent_column(async_db_session: AsyncSession, monkeypatch):
    tenant = Tenant(name="ua-export", slug="ua-export", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()
    async_db_session.add(
        AuditEvent(
            tenant_id=tenant.id,
            actor_user_id=1,
            actor_type="user",
            event_type="user.create",
            outcome="success",
            client_ip="198.51.100.2",
            user_agent="AuditExportTest/2.0",
            request_id="req-export-ua",
            payload={"role": "admin"},
        )
    )
    await async_db_session.flush()

    @asynccontextmanager
    async def _use_test_session():
        yield async_db_session

    monkeypatch.setattr("apps.tenant_app_service.audit.service.app_db_session", _use_test_session)

    stats = AuditExportStats(truncated=False, total_matched=1, exported_count=1)
    chunks: list[bytes] = []
    async for chunk in iter_audit_export_csv(tenant.id, stats=stats, actor_context_user_id=None):
        chunks.append(chunk)
    body = b"".join(chunks).decode("utf-8-sig")
    header_line, data_line, *_ = body.strip().split("\n")
    assert header_line.split(",") == list(AUDIT_EXPORT_HEADERS)
    assert "user_agent" in header_line
    assert "AuditExportTest/2.0" in data_line