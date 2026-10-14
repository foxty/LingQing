"""Tests for Slack image byte loading (document ACL + URL fetch)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.document.types import DocumentImageFile
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import (
    default_image_fetcher,
    fetch_upload_block_bytes,
    make_slack_image_fetcher,
)

PNG = b"\x89PNG\r\n\x1a\nslack-test"
HASH = "f" * 64


def _document_block() -> dict:
    return {
        "source": "document",
        "document_id": 7,
        "filename": f"{HASH}.png",
        "url": f"https://api.example.com/documents/7/images/{HASH}.png",
    }


@pytest.mark.asyncio
async def test_fetch_upload_block_bytes_reads_document_via_service(monkeypatch):
    db = AsyncMock()

    async def fake_read(self, document_id, filename, *, actor):
        assert document_id == 7
        assert filename == f"{HASH}.png"
        assert actor.user_id == 42
        assert actor.user_role == "admin"
        return DocumentImageFile(content=PNG, media_type="image/png")

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.DocumentService.read_document_image",
        fake_read,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.get_file_storage",
        lambda: MagicMock(),
    )

    result = await fetch_upload_block_bytes(
        _document_block(),
        db=db,
        tenant_id=1,
        user_id=42,
        user_role="admin",
    )

    assert result == PNG


@pytest.mark.asyncio
async def test_fetch_upload_block_bytes_returns_none_when_document_missing(monkeypatch):
    async def fake_read(self, *_args, **_kwargs):
        raise ResourceNotFoundError("Document not found: 7")

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.DocumentService.read_document_image",
        fake_read,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.get_file_storage",
        lambda: MagicMock(),
    )

    result = await fetch_upload_block_bytes(
        _document_block(),
        db=AsyncMock(),
        tenant_id=1,
        user_id=42,
        user_role="admin",
    )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_upload_block_bytes_requires_requester_context_for_documents():
    result = await fetch_upload_block_bytes(_document_block())
    assert result is None


@pytest.mark.asyncio
async def test_default_image_fetcher_skips_document_blocks():
    result = await default_image_fetcher(_document_block())
    assert result is None


@pytest.mark.asyncio
async def test_fetch_upload_block_bytes_reads_chart_png_from_disk(monkeypatch, tmp_path):
    name = "chart_9_slack_ab12cd34.png"
    (tmp_path / name).write_bytes(PNG)
    monkeypatch.setattr(
        "apps.shared.chart.paths.get_charts_path",
        lambda: str(tmp_path),
    )
    block = {"source": "chart", "filename": name}
    result = await fetch_upload_block_bytes(block)
    assert result == PNG


@pytest.mark.asyncio
async def test_default_image_fetcher_skips_chart_blocks():
    block = {"source": "chart", "filename": "chart_1_x_ab12cd34.png"}
    result = await default_image_fetcher(block)
    assert result is None


@pytest.mark.asyncio
async def test_make_slack_image_fetcher_delegates_to_document_service(monkeypatch):
    db = AsyncMock()
    calls: list[int] = []

    async def fake_read(self, document_id, filename, *, actor):
        calls.append(document_id)
        return DocumentImageFile(content=PNG, media_type="image/png")

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.DocumentService.read_document_image",
        fake_read,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.get_file_storage",
        lambda: MagicMock(),
    )

    fetch = make_slack_image_fetcher(db=db, tenant_id=9, user_id=3, user_role="member")
    result = await fetch(_document_block())

    assert result == PNG
    assert calls == [7]
