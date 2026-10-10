"""Exception handlers to convert domain exceptions to HTTP responses."""

from fastapi import Request
from fastapi.responses import JSONResponse

from apps.shared.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DomainException,
    DuplicateResourceError,
    InternalServiceError,
    ResourceNotFoundError,
    SQLPreviewError,
    ValidationError,
)
from apps.shared.core.request_context import (
    REQUEST_ID_HEADER,
    format_request_context,
    get_or_create_request_id,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _contract_error_response(
    *,
    request: Request,
    status_code: int,
    fallback_code: str,
    message: str,
    details: dict | None,
) -> JSONResponse:
    safe_details = dict(details or {})
    code = str(safe_details.pop("code", fallback_code))
    request_id = get_or_create_request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": safe_details,
            "request_id": request_id,
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


def register_exception_handlers(app):
    """Register all exception handlers with FastAPI app."""

    @app.exception_handler(ResourceNotFoundError)
    async def handle_not_found(request: Request, exc: ResourceNotFoundError):
        ctx = format_request_context(request)
        logger.warning(f"Not found: {exc.message} ({ctx})")
        return _contract_error_response(
            request=request,
            status_code=404,
            fallback_code="RESOURCE_NOT_FOUND",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(DuplicateResourceError)
    async def handle_duplicate(request: Request, exc: DuplicateResourceError):
        ctx = format_request_context(request)
        logger.warning(f"Duplicate: {exc.message} ({ctx})")
        return _contract_error_response(
            request=request,
            status_code=409,
            fallback_code="RESOURCE_CONFLICT",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(ValidationError)
    async def handle_validation(request: Request, exc: ValidationError):
        ctx = format_request_context(request)
        logger.warning(f"Validation error: {exc.message} ({ctx})")
        return _contract_error_response(
            request=request,
            status_code=400,
            fallback_code="VALIDATION_ERROR",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(AuthenticationError)
    async def handle_authentication(request: Request, exc: AuthenticationError):
        ctx = format_request_context(request)
        logger.warning(f"Auth failed: {exc.message} ({ctx})")
        return _contract_error_response(
            request=request,
            status_code=401,
            fallback_code="AUTHENTICATION_FAILED",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(AuthorizationError)
    async def handle_authorization(request: Request, exc: AuthorizationError):
        ctx = format_request_context(request)
        logger.warning(f"Forbidden: {exc.message} ({ctx})")
        return _contract_error_response(
            request=request,
            status_code=403,
            fallback_code="AUTHORIZATION_FAILED",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(InternalServiceError)
    async def handle_internal_error(request: Request, exc: InternalServiceError):
        ctx = format_request_context(request)
        logger.error(f"Internal error: {exc.message} ({ctx})", exc_info=True)
        return _contract_error_response(
            request=request,
            status_code=500,
            fallback_code="INTERNAL_SERVICE_ERROR",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(SQLPreviewError)
    async def handle_sql_preview_error(request: Request, exc: SQLPreviewError):
        ctx = format_request_context(request)
        logger.warning(f"SQL preview error: {exc.message} ({ctx})")
        return _contract_error_response(
            request=request,
            status_code=400,
            fallback_code="SQL_PREVIEW_ERROR",
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(DomainException)
    async def handle_domain_exception(request: Request, exc: DomainException):
        """Catch-all for unhandled domain exceptions."""
        ctx = format_request_context(request)
        logger.error(f"Domain error: {type(exc).__name__}: {exc.message} ({ctx})", exc_info=True)
        return _contract_error_response(
            request=request,
            status_code=500,
            fallback_code="DOMAIN_ERROR",
            message="Internal server error",
            details={"exception_type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception):
        """Catch-all for unexpected exceptions (non-domain errors).

        These are infrastructure/library errors. Log with full trace + context.
        """
        ctx = format_request_context(request)
        logger.error(
            f"Unexpected {type(exc).__name__}: {str(exc)} ({ctx})",
            exc_info=True,
        )
        return _contract_error_response(
            request=request,
            status_code=500,
            fallback_code="INTERNAL_SERVER_ERROR",
            message="Internal server error",
            details={"exception_type": type(exc).__name__},
        )
