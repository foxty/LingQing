"""DTOs for context resource search."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContextResourceItemDTO(BaseModel):
    """Single context resource search hit."""

    resource_type: str = Field(
        ...,
        description="Resource type: document, dashboard, report, scheduled_task, app, asset",
    )
    resource_id: int = Field(..., description="Primary key of the resource")
    title: str = Field(..., description="Display name")
    subtitle: str | None = Field(None, description="Optional secondary label")


class ContextResourceSearchResponse(BaseModel):
    """Response envelope for context resource search."""

    items: list[ContextResourceItemDTO] = Field(default_factory=list)
