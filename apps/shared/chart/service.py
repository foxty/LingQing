"""Chart artifact lifecycle and authorized image reads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.lifecycle import ArtifactLifecycle
from apps.shared.chart.access import require_chart_read_access, validate_embedded_chart_ids
from apps.shared.chart.embed import chart_markdown_image
from apps.shared.chart.repository import ChartRepository
from apps.shared.chart.storage import (
    ChartImageFormat,
    chart_image_media_type,
    read_chart_artifact_file,
    write_chart_artifact_pair,
)
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class ChartService:
    def __init__(self, *, tenant_id: int, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self._repo = ChartRepository(db)
        self._artifacts = ArtifactLifecycle(
            db=db,
            tenant_id=tenant_id,
            artifact_type=ArtifactType.CHART,
            entity_repo=self._repo,
        )

    @classmethod
    def create(cls, *, tenant_id: int, db: AsyncSession) -> ChartService:
        return cls(tenant_id=tenant_id, db=db)

    async def register_chart(
        self,
        *,
        svg_bytes: bytes,
        png_bytes: bytes,
        owner_id: int,
        thread_id: str,
        title: str,
    ) -> str:
        """Persist chart bytes as an artifact and return canonical markdown."""
        chart = await self._repo.create(
            tenant_id=self.tenant_id,
            owner_id=owner_id,
            thread_id=thread_id,
            title=title,
        )
        write_chart_artifact_pair(self.tenant_id, chart.id, svg_bytes=svg_bytes, png_bytes=png_bytes)
        await self._artifacts.link_on_create(
            resource_id=chart.id,
            owner_id=owner_id,
            title=title,
            url=f"/charts/{chart.id}/image.svg",
            thread_id=thread_id,
            metadata={"chart_id": chart.id, "thread_id": thread_id},
        )
        logger.info(
            "Chart artifact registered id=%s tenant=%s thread=%s (svg %.1f KB, png %.1f KB)",
            chart.id,
            self.tenant_id,
            thread_id,
            len(svg_bytes) / 1024,
            len(png_bytes) / 1024,
        )
        return chart_markdown_image(title, chart.id)

    async def require_read_access(self, *, chart_id: int, actor: ActorContext) -> None:
        await require_chart_read_access(
            db=self.db,
            tenant_id=self.tenant_id,
            actor=actor,
            chart_id=chart_id,
        )

    async def read_image(
        self,
        chart_id: int,
        *,
        fmt: ChartImageFormat,
        actor: ActorContext,
    ) -> tuple[bytes, str]:
        await self.require_read_access(chart_id=chart_id, actor=actor)
        data = read_chart_artifact_file(self.tenant_id, chart_id, fmt=fmt)
        if data is None:
            raise ResourceNotFoundError("Chart image not found")
        return data, chart_image_media_type(fmt)

    async def validate_embedded_chart_ids(self, chart_ids: list[int], *, actor: ActorContext) -> None:
        await validate_embedded_chart_ids(
            db=self.db,
            tenant_id=self.tenant_id,
            actor=actor,
            chart_ids=chart_ids,
        )
