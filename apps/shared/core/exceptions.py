"""Domain-specific exceptions for business logic layer.

Service layer raises these exceptions, API layer converts them to HTTPException.
"""


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ResourceNotFoundError(DomainException):
    """Resource not found (404)."""

    pass


class DuplicateResourceError(DomainException):
    """Resource already exists (409)."""

    pass


class ValidationError(DomainException):
    """Business validation failed (400)."""

    pass


class AuthenticationError(DomainException):
    """Authentication failed (401)."""

    pass


class AuthorizationError(DomainException):
    """Authorization failed (403)."""

    pass


class InternalServiceError(DomainException):
    """Internal service error (500)."""

    pass


class SQLPreviewError(DomainException):
    """Error during SQL preview execution (400)."""

    pass
