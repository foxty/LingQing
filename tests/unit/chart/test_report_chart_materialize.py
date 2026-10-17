"""Report create/update embeds chart ids in metadata (no byte copy)."""

from uuid import uuid4

import pytest

from apps.shared.chart.embed import EMBEDDED_CHART_IDS_METADATA_KEY
from apps.shared.db.models import Tenant, User
from apps.shared.report.service import ReportService

PNG = b"\x89PNG\r\n\x1a\nr"
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'/>"


@pytest.mark.asyncio
async def test_create_report_records_embedded_chart_ids(async_db_session, tmp_path):
    tenant = Tenant(name="tenant_meta", slug=f"tenant_meta_{uuid4().hex[:8]}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username=f"meta_user_{uuid4().hex[:6]}",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    chart_url = "http://127.0.0.1:8000/charts/42/image.svg"
    content = f"# Summary\n\n![Revenue]({chart_url})\n"

    service = ReportService.create(tenant_id=tenant.id, db_session=async_db_session)
    result = await service.create_report(
        title="Q1",
        content=content,
        format="markdown",
        owner_id=user.id,
    )

    assert result.report.content == content
    assert result.report.report_metadata.get(EMBEDDED_CHART_IDS_METADATA_KEY) == [42]
