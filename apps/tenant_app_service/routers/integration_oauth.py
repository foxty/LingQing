"""Shared browser OAuth callback route for user-scoped integrations."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.session import get_db
from apps.tenant_app_service.integration_oauth_callback import handle_integration_oauth_callback

router = APIRouter(prefix="/integrations/oauth", tags=["integrations-oauth"])


@router.get("/callback")
async def integration_oauth_callback(
    db: AsyncSession = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Shared IdP browser callback for user-scoped integrations."""
    return await handle_integration_oauth_callback(
        db=db,
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )