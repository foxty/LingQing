"""Shared OpenAPI fields for integration GET responses."""

from pydantic import BaseModel, Field


class MaskedFieldsMixin(BaseModel):
    """Root-relative dot paths for leaves that mask a stored secret on GET (approach A)."""

    masked_fields: list[str] = Field(
        default_factory=list,
        description="Root-relative dot paths of leaves that mask a stored secret on GET",
    )