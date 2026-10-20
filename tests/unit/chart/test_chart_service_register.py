"""ChartService.register_chart unit tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.chart.service import ChartService


@pytest.mark.asyncio
async def test_register_chart_writes_storage_and_returns_markdown(monkeypatch):
    db = AsyncMock()
    chart_row = SimpleNamespace(id=42)
    link_on_create = AsyncMock()

    monkeypatch.setattr(
        "apps.shared.chart.service.ChartRepository.create",
        AsyncMock(return_value=chart_row),
    )
    write_pair = MagicMock()
    monkeypatch.setattr("apps.shared.chart.service.write_chart_artifact_pair", write_pair)
    monkeypatch.setattr(
        "apps.shared.chart.service.ArtifactLifecycle",
        lambda **kwargs: SimpleNamespace(link_on_create=link_on_create),
    )

    service = ChartService(tenant_id=7, db=db)
    md = await service.register_chart(
        svg_bytes=b"<svg/>",
        png_bytes=b"\x89PNG",
        owner_id=100,
        thread_id="7_100_1",
        title="Test Chart",
    )

    write_pair.assert_called_once_with(7, 42, svg_bytes=b"<svg/>", png_bytes=b"\x89PNG")
    link_on_create.assert_awaited_once()
    assert "/charts/42/image.svg" in md
    assert "![Test Chart]" in md
