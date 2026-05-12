"""Unit tests for create_report with uncommitted thread rows."""

from uuid import uuid4

import pytest

from apps.shared.db.models import ChatThread, Tenant, User
from apps.shared.report.service import ReportService


@pytest.mark.asyncio
async def test_create_report_links_uncommitted_thread_in_same_session(async_db_session):
    tenant = Tenant(name="tenant_headless_report", slug="tenant_headless_report", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="headless_report_user",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    thread_id = f"{tenant.id}_{user.id}_-1_{uuid4()}"
    thread = ChatThread(
        id=thread_id,
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=-1,
        title="Scheduled run",
    )
    async_db_session.add(thread)
    await async_db_session.flush()

    service = ReportService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = await service.create_report(
        title="Daily summary",
        content="Report body",
        format="markdown",
        thread_id=thread_id,
        owner_id=user.id,
        report_metadata={"length": len("Report body")},
    )

    assert result.report.id is not None
    assert result.artifact is not None
