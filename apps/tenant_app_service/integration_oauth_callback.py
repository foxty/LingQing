"""Shared browser OAuth callback handler (FastAPI redirect wiring)."""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthenticationError, ResourceNotFoundError, ValidationError
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.oauth import IntegrationOAuthFlow
from apps.shared.external_systems.oauth.flow import append_oauth_error_hints
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


async def handle_integration_oauth_callback(
    *,
    db: AsyncSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    default_resource_type: str = RESOURCE_TYPE_API_CONNECTOR,
) -> RedirectResponse:
    """Complete browser OAuth for any registered integration resource type."""
    flow = IntegrationOAuthFlow(db)

    def redirect_error(
        *,
        oauth_code: str | None = None,
        oauth_detail: str | None = None,
        oauth_reason: str | None = None,
    ) -> RedirectResponse:
        base = flow.portal_error_url_for_state(state, default_resource_type=default_resource_type)
        return RedirectResponse(
            append_oauth_error_hints(
                base,
                oauth_code=oauth_code,
                oauth_detail=oauth_detail,
                oauth_reason=oauth_reason,
            )
        )

    if error:
        description = (error_description or "").strip()
        logger.warning(
            "Integration OAuth IdP returned error: %s%s",
            error,
            f" — {description}" if description else "",
        )
        return redirect_error(oauth_code=error, oauth_detail=error_description)

    if not code or not state:
        logger.warning(
            "Integration OAuth callback missing code or state (code=%s, state=%s)",
            "present" if code else "missing",
            "present" if state else "missing",
        )
        return redirect_error(oauth_reason="missing_callback_params")

    try:
        outcome = await flow.complete_from_callback(code=code, state=state)
        await db.commit()
        return RedirectResponse(outcome.portal_url)
    except ValidationError as exc:
        await db.rollback()
        logger.warning("Integration OAuth validation failed: %s", exc)
        return redirect_error(oauth_reason=str(exc))
    except AuthenticationError as exc:
        await db.rollback()
        logger.warning("Integration OAuth authentication failed: %s", exc)
        return redirect_error(oauth_reason=str(exc) or "authentication_failed")
    except ResourceNotFoundError as exc:
        await db.rollback()
        logger.warning("Integration OAuth resource not found: %s", exc)
        return redirect_error(oauth_reason=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("Integration OAuth callback failed")
        return redirect_error(
            oauth_reason="token_exchange_failed",
            oauth_detail="Check server logs and verify redirect URI and OAuth app credentials.",
        )