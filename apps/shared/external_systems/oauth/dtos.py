"""Presentation DTOs for integration OAuth (shared across resource routers)."""

from __future__ import annotations

from pydantic import BaseModel


class IntegrationOAuthStartResponse(BaseModel):
    """Browser authorization URL returned from ``…/oauth/start`` endpoints."""

    authorization_url: str