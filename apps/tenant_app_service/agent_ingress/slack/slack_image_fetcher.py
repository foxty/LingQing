"""Fetch image bytes for Slack upload (document ACL + chart static files + owned URLs)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_file_storage
from apps.shared.chart.paths import read_chart_static_png_file
from apps.shared.document.service import DocumentService
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import SlackImageUploadSource

logger = get_logger(__name__)

IMAGE_FETCH_MAX_BYTES = 8 * 1024 * 1024
ImageFetcher = Callable[[dict[str, Any]], Awaitable[bytes | None]]

_CONTEXT_ONLY_SOURCES = frozenset({SlackImageUploadSource.DOCUMENT, SlackImageUploadSource.CHART})


def is_raster_image(data: bytes) -> bool:
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or data.startswith((b"GIF87a", b"GIF89a"))
    )


def _reject_oversized(data: bytes, *, context: str) -> bool:
    if len(data) <= IMAGE_FETCH_MAX_BYTES:
        return False
    logger.warning(
        "Slack image exceeds %s byte limit (%s bytes): %s",
        IMAGE_FETCH_MAX_BYTES,
        len(data),
        context,
    )
    return True


async def fetch_owned_url_bytes(url: str) -> bytes | None:
    """Download raster bytes from an owned origin. Redirects are not followed."""
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp is unavailable; skipping Slack image fetch")
        return None

    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    return None
                data = await response.content.read(IMAGE_FETCH_MAX_BYTES + 1)
    except Exception as exc:
        logger.warning("Slack image fetch failed: %s", exc)
        return None
    if _reject_oversized(data, context=url):
        return None
    if is_raster_image(data):
        return data
    logger.warning("Slack image fetch returned non-raster bytes from %s", url)
    return None


def _chart_png_bytes(filename: str) -> bytes | None:
    data = read_chart_static_png_file(filename)
    if data is None:
        logger.warning("Slack chart PNG not found on disk: %s", filename)
        return None
    if _reject_oversized(data, context=f"chart:{filename}"):
        return None
    if not is_raster_image(data):
        logger.warning("Slack chart file is not raster PNG: %s", filename)
        return None
    return data


async def fetch_upload_block_bytes(
    block: dict[str, Any],
    *,
    db: AsyncSession | None = None,
    tenant_id: int | None = None,
    user_id: int | None = None,
    user_role: str | None = None,
) -> bytes | None:
    """Load raster bytes for one ``_image_upload`` block."""
    source = block.get("source")
    if source == SlackImageUploadSource.CHART:
        filename = block.get("filename")
        if not isinstance(filename, str):
            logger.warning("Slack chart upload block missing filename")
            return None
        return _chart_png_bytes(filename)

    if source == SlackImageUploadSource.DOCUMENT:
        if db is None or tenant_id is None or user_id is None or not user_role:
            logger.warning("Slack document image fetch missing tenant/user context")
            return None
        document_id = block.get("document_id")
        filename = block.get("filename")
        if not isinstance(document_id, int) or not isinstance(filename, str):
            logger.warning("Slack document upload block missing document_id or filename")
            return None
        try:
            service = DocumentService(tenant_id, db, get_file_storage())
            actor = ActorContext(tenant_id=tenant_id, user_id=user_id, user_role=user_role)
            image = await service.read_document_image(
                document_id,
                filename,
                actor=actor,
            )
        except Exception as exc:
            logger.warning("Slack document image read failed: %s", exc)
            return None
        if _reject_oversized(image.content, context=f"document:{document_id}/{filename}"):
            return None
        if not is_raster_image(image.content):
            logger.warning("Slack document image is not raster: document=%s file=%s", document_id, filename)
            return None
        return image.content

    url = str(block.get("url") or "")
    if not url:
        logger.warning("Slack image upload block missing url (source=%s)", source)
        return None
    return await fetch_owned_url_bytes(url)


async def default_image_fetcher(block: dict[str, Any]) -> bytes | None:
    """URL-only fetcher when no document requester context is available."""
    source = block.get("source")
    if source in _CONTEXT_ONLY_SOURCES:
        logger.warning(
            "Slack default image fetcher cannot load %s blocks; use make_slack_image_fetcher",
            source,
        )
        return None
    return await fetch_upload_block_bytes(block)


def make_slack_image_fetcher(
    *,
    db: AsyncSession,
    tenant_id: int,
    user_id: int,
    user_role: str,
) -> ImageFetcher:
    """Build a fetcher that honors document ACL for the linked Slack user."""

    async def fetch(block: dict[str, Any]) -> bytes | None:
        return await fetch_upload_block_bytes(
            block,
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
        )

    return fetch
