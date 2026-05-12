"""Core application infrastructure.

Provides:
- Domain exceptions for business logic
- Authentication and authorization
- Exception handlers for API layer
- Transaction management
- Base service classes
"""

from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DomainException,
    DuplicateResourceError,
    InternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)

__all__ = [
    # Base Service
    "TenantAwareService",
    # Exceptions
    "DomainException",
    "ResourceNotFoundError",
    "DuplicateResourceError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "InternalServiceError",
]
