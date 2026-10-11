"""Upload private images once and reuse for Block Kit and Canvas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort
from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import image_upload_block_for_src
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import ImageFetcher, is_raster_image
from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import (
    iter_markdown_image_refs,
    upload_block_cache_key,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedSlackImage:
    file_id: str
    permalink: str | None


class SlackAssetResolver:
    """Resolve private images to Slack-hosted files (shared by blocks and Canvas)."""

    def __init__(
        self,
        *,
        client: SlackClientPort,
        bot_token: str,
        image_fetcher: ImageFetcher,
    ):
        self.client = client
        self.bot_token = bot_token
        self.image_fetcher = image_fetcher
        self._cache: dict[str, ResolvedSlackImage] = {}

    async def resolve_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != "_image_upload":
                resolved.append(block)
                continue
            resolved.append(await self._resolve_upload_block(block))
        return resolved

    async def prepare_canvas_markdown(
        self,
        markdown: str,
        *,
        portal_origin: str | None,
        api_origin: str | None,
    ) -> str:
        """Rewrite private image refs to Slack file permalinks where possible."""
        updated = markdown
        for alt, src in iter_markdown_image_refs(markdown):
            upload = image_upload_block_for_src(
                src,
                alt,
                portal_origin=portal_origin,
                api_origin=api_origin,
            )
            if upload is None:
                continue
            resolved = await self._ensure_upload(upload)
            if not resolved.permalink:
                continue
            if alt:
                old = f"![{alt}]({src})"
                new = f"![{alt}]({resolved.permalink})"
            else:
                old = f'src="{src}"'
                new = f'src="{resolved.permalink}"'
            if old in updated:
                updated = updated.replace(old, new, 1)
        return updated

    async def _resolve_upload_block(self, block: dict[str, Any]) -> dict[str, Any]:
        fallback = str(block.get("fallback_mrkdwn") or block.get("alt_text") or "image")
        try:
            resolved = await self._ensure_upload(block)
        except Exception as exc:
            logger.warning("Slack image upload failed: %s", exc)
            return {"type": "section", "text": {"type": "mrkdwn", "text": fallback}}
        return {
            "type": "image",
            "slack_file": {"id": resolved.file_id},
            "alt_text": block.get("alt_text") or "image",
        }

    async def _ensure_upload(self, block: dict[str, Any]) -> ResolvedSlackImage:
        cache_key = upload_block_cache_key(block)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self.image_fetcher(block)
        if not data or not is_raster_image(data):
            raise ValueError("image bytes are missing or not a supported raster image")

        filename = str(block.get("upload_filename") or block.get("filename") or "image.png")
        file_id = await self.client.upload_file(
            bot_token=self.bot_token,
            filename=filename,
            content=data,
        )
        permalink = await self.client.file_permalink(bot_token=self.bot_token, file_id=file_id)
        resolved = ResolvedSlackImage(file_id=file_id, permalink=permalink)
        self._cache[cache_key] = resolved
        return resolved
