"""Constants for API connector domain and service logic."""

from __future__ import annotations

from typing import Final

# Authentication types supported by API connector
# - none: No authentication required
# - api_key: Static API key in custom header (e.g., X-API-Key)
# - bearer: Bearer token in Authorization header
# - basic: HTTP Basic Authentication
# - custom: Custom/session-based auth with configurable headers and login flow
AUTH_TYPE_NONE: Final = "none"
AUTH_TYPE_API_KEY: Final = "api_key"
AUTH_TYPE_BEARER: Final = "bearer"
AUTH_TYPE_BASIC: Final = "basic"
AUTH_TYPE_CUSTOM: Final = "custom"

SCHEMA_SOURCE_TYPE_MANUAL: Final = "manual"
SCHEMA_SOURCE_TYPE_OPENAPI_URL: Final = "openapi_url"
SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD: Final = "openapi_upload"

CONNECTOR_STATUS_ACTIVE: Final = "active"
CONNECTOR_STATUS_DISABLED: Final = "disabled"

OPERATION_STATUS_ACTIVE: Final = "active"
OPERATION_STATUS_DISABLED: Final = "disabled"
OPERATION_STATUS_STALE: Final = "stale"

OPERATION_SOURCE_IMPORTED: Final = "imported"
OPERATION_SOURCE_MANUAL: Final = "manual"

AUTH_REQUIREMENT_REQUIRED: Final = "required"
AUTH_REQUIREMENT_NONE: Final = "none"

RISK_LEVEL_LOW: Final = "low"
RISK_LEVEL_MEDIUM: Final = "medium"
RISK_LEVEL_HIGH: Final = "high"

DEFAULT_HTTP_TIMEOUT_MS: Final = 30000
DEFAULT_MAX_RETRIES: Final = 0
DEFAULT_RETRY_BACKOFF_MS: Final = 200
DEFAULT_RETRY_ON_STATUS: Final = (429, 502, 503, 504)
DEFAULT_MAX_REQUESTS_PER_SECOND: Final = 0.0
DEFAULT_MAX_CONCURRENT_REQUESTS: Final = 0

HTTP_METHOD_GET: Final = "GET"
HTTP_METHOD_POST: Final = "POST"
HTTP_METHOD_PUT: Final = "PUT"
HTTP_METHOD_PATCH: Final = "PATCH"
HTTP_METHOD_DELETE: Final = "DELETE"
HTTP_METHOD_HEAD: Final = "HEAD"
HTTP_METHOD_OPTIONS: Final = "OPTIONS"

ALLOWED_HTTP_METHODS: Final = frozenset(
    {
        HTTP_METHOD_GET,
        HTTP_METHOD_POST,
        HTTP_METHOD_PUT,
        HTTP_METHOD_PATCH,
        HTTP_METHOD_DELETE,
        HTTP_METHOD_HEAD,
        HTTP_METHOD_OPTIONS,
    }
)

ALLOWED_HTTP_METHODS_LOWER: Final = frozenset(method.lower() for method in ALLOWED_HTTP_METHODS)
