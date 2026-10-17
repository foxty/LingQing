"""Integration: chart artifact read ACL and transitive report embed access."""

from __future__ import annotations

import re
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.shared.chart.embed import chart_id_from_image_url
from apps.shared.chart.service import ChartService
from apps.shared.chart.storage import CHART_IMAGE_FORMAT_PNG
from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.models import AclGrant
from apps.shared.domain.actor import ActorContext
from apps.shared.report.service import ReportService
from tests.integration.tool_integration_helpers import seed_actor_records, seed_base_records

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\nx"
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@pytest.fixture
def chart_storage_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "apps.shared.chart.embed.EnvConfig",
        SimpleNamespace(CHART_SERVICE_URL="http://127.0.0.1:8000"),
    )
    monkeypatch.setattr(
        "apps.shared.chart.storage.get_tenant_media_path",
        lambda tenant_id: str(tmp_path / f"tenant_{tenant_id}"),
    )
    return tmp_path


def _chart_id_from_markdown(markdown: str) -> int:
    match = _MARKDOWN_IMAGE.search(markdown)
    assert match is not None
    chart_id = chart_id_from_image_url(match.group(1))
    assert chart_id is not None
    return chart_id


async def _register_chart(
    session,
    *,
    tenant_id: int,
    owner_id: int,
    thread_id: str,
    title: str = "Integration chart",
) -> int:
    service = ChartService.create(tenant_id=tenant_id, db=session)
    markdown = await service.register_chart(
        svg_bytes=SVG,
        png_bytes=PNG,
        owner_id=owner_id,
        thread_id=thread_id,
        title=title,
    )
    await session.commit()
    return _chart_id_from_markdown(markdown)


@pytest.mark.asyncio
async def test_owner_can_read_registered_chart(async_db_session, runtime_context, chart_storage_root):
    await seed_base_records(async_db_session, runtime_context)
    tenant_id = runtime_context.user.tenant_id
    owner_id = runtime_context.user.user_id
    thread_id = runtime_context.thread_id

    chart_id = await _register_chart(
        async_db_session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        thread_id=thread_id,
    )

    service = ChartService.create(tenant_id=tenant_id, db=async_db_session)
    actor = ActorContext(tenant_id=tenant_id, user_id=owner_id, user_role=runtime_context.user.role)
    data, media_type = await service.read_image(chart_id, fmt=CHART_IMAGE_FORMAT_PNG, actor=actor)

    assert data == PNG
    assert media_type == "image/png"


@pytest.mark.asyncio
async def test_other_user_denied_direct_chart_read(async_db_session, runtime_context, chart_storage_root):
    await seed_base_records(async_db_session, runtime_context)
    other_id = 8801
    other_thread = f"thread_other_{uuid4().hex[:8]}"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=other_id,
        username=f"other_{uuid4().hex[:6]}",
        role="member",
        thread_id=other_thread,
    )

    tenant_id = runtime_context.user.tenant_id
    chart_id = await _register_chart(
        async_db_session,
        tenant_id=tenant_id,
        owner_id=runtime_context.user.user_id,
        thread_id=runtime_context.thread_id,
    )

    service = ChartService.create(tenant_id=tenant_id, db=async_db_session)
    other_actor = ActorContext(tenant_id=tenant_id, user_id=other_id, user_role="member")

    with pytest.raises(AuthorizationError):
        await service.read_image(chart_id, fmt=CHART_IMAGE_FORMAT_PNG, actor=other_actor)


@pytest.mark.asyncio
async def test_chart_read_via_report_share_transitive(async_db_session, runtime_context, chart_storage_root):
    await seed_base_records(async_db_session, runtime_context)
    other_id = 8802
    other_thread = f"thread_reader_{uuid4().hex[:8]}"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=other_id,
        username=f"reader_{uuid4().hex[:6]}",
        role="member",
        thread_id=other_thread,
    )

    tenant_id = runtime_context.user.tenant_id
    owner_id = runtime_context.user.user_id
    thread_id = runtime_context.thread_id
    chart_id = await _register_chart(
        async_db_session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        thread_id=thread_id,
    )

    chart_url = f"http://127.0.0.1:8000/charts/{chart_id}/image.svg"
    report_service = ReportService.create(tenant_id=tenant_id, db_session=async_db_session)
    created = await report_service.create_report(
        title="Report with chart",
        content=f"![Chart]({chart_url})",
        owner_id=owner_id,
        format="markdown",
        thread_id=thread_id,
    )
    report_id = created.report.id
    await async_db_session.commit()

    service = ChartService.create(tenant_id=tenant_id, db=async_db_session)
    other_actor = ActorContext(tenant_id=tenant_id, user_id=other_id, user_role="member")

    with pytest.raises(AuthorizationError):
        await service.read_image(chart_id, fmt=CHART_IMAGE_FORMAT_PNG, actor=other_actor)

    async_db_session.add(
        AclGrant(
            tenant_id=tenant_id,
            resource_type="report",
            resource_id=report_id,
            principal_type="user",
            principal_id=str(other_id),
            permission="read",
            effect="allow",
            created_by=owner_id,
        )
    )
    await async_db_session.commit()

    data, _ = await service.read_image(chart_id, fmt=CHART_IMAGE_FORMAT_PNG, actor=other_actor)
    assert data == PNG


@pytest.mark.asyncio
async def test_report_update_rejects_foreign_chart_embed(async_db_session, runtime_context, chart_storage_root):
    await seed_base_records(async_db_session, runtime_context)
    editor_id = 8803
    editor_thread = f"thread_editor_{uuid4().hex[:8]}"
    await seed_actor_records(
        async_db_session,
        runtime_context,
        user_id=editor_id,
        username=f"editor_{uuid4().hex[:6]}",
        role="member",
        thread_id=editor_thread,
    )

    tenant_id = runtime_context.user.tenant_id
    owner_id = runtime_context.user.user_id
    chart_id = await _register_chart(
        async_db_session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        thread_id=runtime_context.thread_id,
    )

    report_service = ReportService.create(tenant_id=tenant_id, db_session=async_db_session)
    created = await report_service.create_report(
        title="Editor report",
        content="No charts yet",
        owner_id=editor_id,
        format="markdown",
        thread_id=editor_thread,
    )
    report_id = created.report.id
    await async_db_session.commit()

    editor_actor = ActorContext(tenant_id=tenant_id, user_id=editor_id, user_role="member")
    foreign_chart_url = f"http://127.0.0.1:8000/charts/{chart_id}/image.svg"

    with pytest.raises(AuthorizationError):
        await report_service.update_report_for_actor(
            report_id,
            actor=editor_actor,
            content=f"![Stolen]({foreign_chart_url})",
        )
