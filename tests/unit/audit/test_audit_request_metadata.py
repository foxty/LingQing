"""Audit rows must inherit HTTP metadata from request-scoped context."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.recorder import ACTOR_TYPE_USER, OUTCOME_SUCCESS, TenantAuditRecorder
from apps.shared.core.request_context import RequestLoggingMiddleware
from apps.shared.db.models import AuditEvent, Tenant


@pytest.mark.asyncio
async def test_recorder_persists_http_metadata_from_request_scope(async_db_session: AsyncSession):
    """Request-scoped context (as set by middleware) fills client_ip, user_agent, request_id."""
    tenant = Tenant(name="meta-t", slug="meta-t", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/_audit_metadata_probe")
    async def _probe():
        recorder = TenantAuditRecorder(async_db_session, tenant_id=tenant.id)
        await recorder.record(
            event_type="skill.status.update",
            outcome=OUTCOME_SUCCESS,
            actor_user_id=99,
            actor_type=ACTOR_TYPE_USER,
            resource_type="skill",
            resource_id="probe-skill",
            payload={"previous_status": False, "new_status": True},
        )
        await async_db_session.flush()
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/_audit_metadata_probe",
            headers={
                "X-Forwarded-For": "203.0.113.50, 198.51.100.1",
                "User-Agent": "AuditMetadataTest/1.0",
                "X-Request-ID": "req-metadata-001",
            },
        )
    assert resp.status_code == 200

    result = await async_db_session.execute(
        select(AuditEvent).where(
            AuditEvent.tenant_id == tenant.id,
            AuditEvent.event_type == "skill.status.update",
        )
    )
    row = result.scalar_one()
    assert row.client_ip is not None, "client_ip must be set from request"
    assert row.user_agent == "AuditMetadataTest/1.0"
    assert row.request_id == "req-metadata-001"
    assert row.client_ip == "203.0.113.50"