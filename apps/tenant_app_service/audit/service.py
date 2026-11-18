"""Audit log query and export application service."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.context import AuditRequestContext
from apps.shared.audit_event.event_types import TenantAuditEventType
from apps.shared.audit_event.recorder import (
    ACTOR_TYPE_USER,
    OUTCOME_SUCCESS,
    TenantAuditRecorder,
)
from apps.shared.audit_event.repository import DEFAULT_PAGE_SIZE, AuditEventRepository
from apps.shared.db.models import AuditEvent
from apps.shared.db.session import app_db_session
from apps.shared.utils.structured_export import CsvTableExporter
from apps.tenant_app_service.audit.schemas import AuditEventItem, AuditEventListResponse

AUDIT_EXPORT_HEADERS = (
    "id",
    "created_at",
    "event_type",
    "outcome",
    "actor_user_id",
    "actor_type",
    "resource_type",
    "resource_id",
    "client_ip",
    "user_agent",
    "request_id",
    "payload_json",
)

UTF8_BOM = "\ufeff"


@dataclass(frozen=True, slots=True)
class AuditExportStats:
    truncated: bool
    total_matched: int
    exported_count: int


def _to_item(row: AuditEvent) -> AuditEventItem:
    return AuditEventItem(
        id=row.id,
        tenant_id=row.tenant_id,
        actor_user_id=row.actor_user_id,
        actor_type=row.actor_type,
        event_type=row.event_type,
        outcome=row.outcome,
        client_ip=row.client_ip,
        user_agent=row.user_agent,
        request_id=row.request_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        payload=row.payload,
        created_at=row.created_at,
    )


class TenantAuditQueryService:
    """Read-side audit log operations for a tenant."""

    def __init__(self, tenant_id: int, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self._repo = AuditEventRepository(db)

    async def list_events(
        self,
        *,
        actor_user_id: int | None = None,
        event_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> AuditEventListResponse:
        rows, total = await self._repo.list_paginated(
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            from_dt=from_dt,
            to_dt=to_dt,
            page=page,
            page_size=page_size,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return AuditEventListResponse(
            items=[_to_item(row) for row in rows],
            total=total,
            page=max(1, page),
            page_size=page_size,
            total_pages=total_pages,
        )

    async def export_stats(
        self,
        *,
        actor_user_id: int | None = None,
        event_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> AuditExportStats:
        rows, total_matched, truncated = await self._repo.list_for_export(
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        return AuditExportStats(
            truncated=truncated,
            total_matched=total_matched,
            exported_count=len(rows),
        )


def _row_to_csv_cells(row: AuditEvent) -> list:
    payload_json = json.dumps(row.payload, ensure_ascii=False, separators=(",", ":")) if row.payload else ""
    return [
        row.id,
        row.created_at.isoformat(),
        row.event_type,
        row.outcome or "",
        row.actor_user_id if row.actor_user_id is not None else "",
        row.actor_type or "",
        row.resource_type or "",
        row.resource_id or "",
        row.client_ip or "",
        row.user_agent or "",
        row.request_id or "",
        payload_json,
    ]


async def iter_audit_export_csv(
    tenant_id: int,
    *,
    actor_user_id: int | None = None,
    event_type: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    actor_context_user_id: int | None = None,
    request_context: AuditRequestContext | None = None,
    filter_summary: dict | None = None,
    stats: AuditExportStats | None = None,
) -> AsyncIterator[bytes]:
    """Stream audit CSV with UTF-8 BOM; records ``audit.log.export`` before streaming row data."""
    yield UTF8_BOM.encode("utf-8")
    exporter = CsvTableExporter()
    exporter.write_header(AUDIT_EXPORT_HEADERS)
    data_chunk: bytes | None = None

    async with app_db_session() as db:
        repo = AuditEventRepository(db)
        if stats is None:
            rows, total_matched, truncated = await repo.list_for_export(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                from_dt=from_dt,
                to_dt=to_dt,
            )
            stats = AuditExportStats(
                truncated=truncated,
                total_matched=total_matched,
                exported_count=len(rows),
            )
        else:
            rows, _, _ = await repo.list_for_export(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                from_dt=from_dt,
                to_dt=to_dt,
            )

        if actor_context_user_id is not None:
            recorder = TenantAuditRecorder(
                db,
                tenant_id=tenant_id,
                request_context=request_context,
            )
            await recorder.record(
                event_type=TenantAuditEventType.AUDIT_LOG_EXPORT.value,
                outcome=OUTCOME_SUCCESS,
                actor_user_id=actor_context_user_id,
                actor_type=ACTOR_TYPE_USER,
                resource_type="audit_export",
                resource_id=request_context.request_id if request_context else None,
                payload={
                    "filter_summary": filter_summary or {},
                    "exported_count": stats.exported_count,
                    "truncated": stats.truncated,
                    "total_matched": stats.total_matched,
                },
            )

        for row in rows:
            exporter.append_row(_row_to_csv_cells(row))
        data_chunk = exporter.flush_chunk()

    if data_chunk:
        yield data_chunk