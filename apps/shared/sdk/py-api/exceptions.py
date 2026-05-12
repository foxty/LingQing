"""Custom exceptions for LingQing SDK."""


class SDKError(Exception):
    """Base exception for SDK errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthError(SDKError):
    """Authentication or authorization error."""

    pass


class APIError(SDKError):
    """API call failed with non-2xx status code."""

    def __init__(self, message: str, status_code: int, body: dict | None = None):
        self.body = body
        super().__init__(message, status_code)


class ValidationError(SDKError):
    """Request validation error."""

    pass
