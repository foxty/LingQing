"""Shared browser OAuth callback handler (FastAPI redirect wiring)."""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthenticationError, ResourceNotFoundError, ValidationError
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.oauth import IntegrationOAuthFlow


async def handle_integration_oauth_callback(
    *,
    db: AsyncSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    default_resource_type: str = RESOURCE_TYPE_API_CONNECTOR,
) -> RedirectResponse:
    """Complete browser OAuth for any registered integration resource type."""
    flow = IntegrationOAuthFlow(db)
    if error or not code or not state:
        return RedirectResponse(flow.portal_error_url_for_state(state, default_resource_type=default_resource_type))

    try:
        outcome = await flow.complete_from_callback(code=code, state=state)
        await db.commit()
        return RedirectResponse(outcome.portal_url)
    except (AuthenticationError, ResourceNotFoundError, ValidationError):
        await db.rollback()
        return RedirectResponse(flow.portal_error_url_for_state(state, default_resource_type=default_resource_type))