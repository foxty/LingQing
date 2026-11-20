"""Audit query/export API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEventItem(BaseModel):
    id: int
    tenant_id: int
    actor_user_id: int | None
    actor_username: str | None = None
    actor_type: str | None
    event_type: str
    outcome: str | None
    client_ip: str | None
    user_agent: str | None
    request_id: str | None
    resource_type: str | None
    resource_id: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class AuditEventTypesResponse(BaseModel):
    items: list[str]


class AuditExportMeta(BaseModel):
    truncated: bool
    total_matched: int
    exported_count: int = Field(description="Rows included in this CSV response")