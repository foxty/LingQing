"""Domain models for API connector business layer."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Sequence

from apps.shared.api_connector.constants import (
    AUTH_REQUIREMENT_NONE,
    AUTH_REQUIREMENT_REQUIRED,
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_CUSTOM,
    AUTH_TYPE_NONE,
    CONNECTOR_STATUS_ACTIVE,
    CONNECTOR_STATUS_DISABLED,
    DEFAULT_HTTP_TIMEOUT_MS,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_MAX_REQUESTS_PER_SECOND,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_MS,
    DEFAULT_RETRY_ON_STATUS,
    OPERATION_SOURCE_IMPORTED,
    OPERATION_SOURCE_MANUAL,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
    RISK_LEVEL_HIGH,
    RISK_LEVEL_LOW,
    RISK_LEVEL_MEDIUM,
    SCHEMA_SOURCE_TYPE_MANUAL,
    SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD,
    SCHEMA_SOURCE_TYPE_OPENAPI_URL,
)
from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.base_domain_model import BaseDomainModel

AuthType = Literal[AUTH_TYPE_NONE, AUTH_TYPE_API_KEY, AUTH_TYPE_BEARER, AUTH_TYPE_BASIC, AUTH_TYPE_CUSTOM]
SchemaSourceType = Literal[
    SCHEMA_SOURCE_TYPE_MANUAL,
    SCHEMA_SOURCE_TYPE_OPENAPI_URL,
    SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD,
]
ConnectorStatus = Literal[CONNECTOR_STATUS_ACTIVE, CONNECTOR_STATUS_DISABLED]
AuthRequirement = Literal[AUTH_REQUIREMENT_REQUIRED, AUTH_REQUIREMENT_NONE]
RiskLevel = Literal[RISK_LEVEL_LOW, RISK_LEVEL_MEDIUM, RISK_LEVEL_HIGH]
OperationStatus = Literal[OPERATION_STATUS_ACTIVE, OPERATION_STATUS_DISABLED, OPERATION_STATUS_STALE]
OperationSource = Literal[OPERATION_SOURCE_IMPORTED, OPERATION_SOURCE_MANUAL]


# Auth config value objects (pure domain dataclasses)
# These are internal domain models with no framework dependencies.
# Pydantic validation happens at the API boundary (schemas.py).


@dataclass
class ApiKeyAuthConfig:
    """API Key authentication configuration."""

    auth_method: str = "api_key"
    key_name: str = "X-API-Key"
    key_value: str | None = None
    api_key: str | None = None


@dataclass
class BearerAuthConfig:
    """Bearer token authentication configuration."""

    auth_method: str = "bearer"
    token: str | None = None
    access_token: str | None = None


@dataclass
class BasicAuthConfig:
    """HTTP Basic authentication configuration."""

    auth_method: str = "basic"
    username: str | None = None
    password: str | None = None


@dataclass
class NoAuthConfig:
    """No authentication configuration (open access)."""

    auth_method: str = "none"


@dataclass
class CustomAuthConfig:
    """Configuration for custom/session-based authentication.

    Generic pattern for enterprise systems (Kingdee, SAP, Oracle, etc.) that use:
    1. Login endpoint to obtain session tokens
    2. Custom headers with those tokens for authenticated requests

    Example (Kingdee ERP):
        {
            "auth_method": "custom",
            "login_endpoint": "/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc",
            "login_method": "POST",
            "login_payload_template": {
                "parameters": ["{account_id}", "{username}", "{app_key}", "{app_secret}", 2052]
            },
            "token_extraction": {
                "token": "Context.UserToken",
                "session_id": "Context.SessionId"
            },
            "request_headers": {
                "X-User-Token": "{token}",
                "X-Session-Id": "{session_id}"
            },
            "extra_config": {
                "account_id": "YOUR_DATACENTER_ID",
                "username": "admin",
                "app_key": "your-app-key",
                "app_secret": "your-secret",
                "token_ttl_seconds": 1800
            }
        }

    Placeholders in templates are replaced with values from extra_config at runtime.
    Tokens are cached for token_ttl_seconds (default 1800s) to avoid repeated logins.
    """

    auth_method: str = "custom"
    login_endpoint: str = ""
    login_method: str = "POST"
    login_payload_template: dict[str, Any] = field(default_factory=dict)
    token_extraction: dict[str, str] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)


# Union type for all auth config variants
AuthConfig = NoAuthConfig | ApiKeyAuthConfig | BearerAuthConfig | BasicAuthConfig | CustomAuthConfig


@dataclass
class RatePolicyDomain(BaseDomainModel):
    timeout_ms: int = DEFAULT_HTTP_TIMEOUT_MS
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff_ms: int = DEFAULT_RETRY_BACKOFF_MS
    retry_on_status: tuple[int, ...] = field(default_factory=lambda: tuple(DEFAULT_RETRY_ON_STATUS))
    max_requests_per_second: float = DEFAULT_MAX_REQUESTS_PER_SECOND
    burst_size: int | None = None
    max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any] | None) -> RatePolicyDomain:
        data = raw or {}
        timeout_ms = cls._to_int(data.get("timeout_ms", DEFAULT_HTTP_TIMEOUT_MS), minimum=1)
        max_retries = cls._to_int(data.get("max_retries", DEFAULT_MAX_RETRIES), minimum=0)
        retry_backoff_ms = cls._to_int(data.get("retry_backoff_ms", DEFAULT_RETRY_BACKOFF_MS), minimum=1)

        retry_on_status_raw = data.get("retry_on_status", DEFAULT_RETRY_ON_STATUS)
        retry_on_status = cls._normalize_status_codes(retry_on_status_raw)

        max_requests_per_second = cls._to_float(
            data.get("max_requests_per_second", DEFAULT_MAX_REQUESTS_PER_SECOND),
            minimum=0.0,
        )

        burst_size_raw = data.get("burst_size")
        burst_size = None if burst_size_raw is None else cls._to_int(burst_size_raw, minimum=1)
        max_concurrent_requests = cls._to_int(
            data.get("max_concurrent_requests", DEFAULT_MAX_CONCURRENT_REQUESTS),
            minimum=0,
        )

        return cls(
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
            retry_on_status=retry_on_status,
            max_requests_per_second=max_requests_per_second,
            burst_size=burst_size,
            max_concurrent_requests=max_concurrent_requests,
        )

    def retry_on_status_set(self) -> set[int]:
        return set(self.retry_on_status)

    def burst_size_value(self) -> int:
        if self.burst_size is not None:
            return self.burst_size
        if self.max_requests_per_second >= 1:
            return max(int(self.max_requests_per_second), 1)
        return 1

    def to_policy_dict(self) -> dict[str, Any]:
        return {
            "timeout_ms": self.timeout_ms,
            "max_retries": self.max_retries,
            "retry_backoff_ms": self.retry_backoff_ms,
            "retry_on_status": list(self.retry_on_status),
            "max_requests_per_second": self.max_requests_per_second,
            "burst_size": self.burst_size_value(),
            "max_concurrent_requests": self.max_concurrent_requests,
        }

    @staticmethod
    def _normalize_status_codes(raw: Any) -> tuple[int, ...]:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return tuple(DEFAULT_RETRY_ON_STATUS)

        values: list[int] = []
        for code in raw:
            try:
                parsed = int(code)
            except (TypeError, ValueError):
                continue
            if parsed not in values:
                values.append(parsed)

        return tuple(values) if values else tuple(DEFAULT_RETRY_ON_STATUS)

    @staticmethod
    def _to_int(value: Any, *, minimum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = minimum
        return max(parsed, minimum)

    @staticmethod
    def _to_float(value: Any, *, minimum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = minimum
        return max(parsed, minimum)


@dataclass
class LoginConfig:
    """Login flow configuration for custom authentication.

    Encapsulates all information needed to perform automatic login and token extraction.
    """

    login_endpoint: str
    login_method: str = "POST"
    login_payload_template: dict[str, Any] = field(default_factory=dict)
    token_extraction: dict[str, str] = field(default_factory=dict)
    extra_config: dict[str, Any] = field(default_factory=dict)
    token_ttl_seconds: int = 1800


@dataclass
class ApiConnectorDomain(BaseDomainModel):
    id: int
    tenant_id: int
    owner_id: int
    name: str
    description: str | None
    base_url: str
    auth_type: AuthType
    auth_config: AuthConfig
    rate_policy: RatePolicyDomain
    schema_source_type: SchemaSourceType
    schema_source_url: str | None
    schema_metadata: dict[str, Any]
    schema_last_synced_at: datetime | None
    status: ConnectorStatus
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None

    def build_headers(self, extra_headers: dict[str, Any] | None = None) -> dict[str, str]:
        """Build HTTP headers for API request based on authentication type.

        This method encapsulates all authentication-specific header building logic.
        Validation is automatic via Pydantic's AuthConfig types (ApiKeyAuthConfig, etc.).

        Args:
            extra_headers: Additional headers from operation call parameters

        Returns:
            Dictionary of HTTP headers to include in API request

        Raises:
            ValidationError: If required auth fields are missing for the auth_type
        """
        auth_config = self.auth_config

        headers: dict[str, str] = {"User-Agent": "LingQing-ApiConnector/1.0"}
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})

        match self.auth_type:
            case "api_key":
                key_name = auth_config.key_name or "X-API-Key"
                key_value = auth_config.key_value or auth_config.api_key
                if not key_value:
                    raise ValidationError("Missing api_key/key_value in auth_config")
                headers[key_name] = str(key_value)

            case "bearer":
                token = auth_config.token or auth_config.access_token
                if not token:
                    raise ValidationError("Missing bearer token in auth_config")
                headers["Authorization"] = f"Bearer {token}"

            case "basic":
                username = auth_config.username
                password = auth_config.password
                if not username or not password:
                    raise ValidationError("Missing username/password for basic auth")
                raw = f"{username}:{password}".encode()
                headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('utf-8')}"

            case "custom":
                # For custom auth, headers are built dynamically during request execution
                # (login flow, token extraction, placeholder substitution)
                # This method returns static headers only; dynamic headers are handled in execution service
                if hasattr(auth_config, "request_headers"):
                    custom_headers = auth_config.request_headers
                    if isinstance(custom_headers, dict):
                        for key, value in custom_headers.items():
                            headers[str(key)] = str(value)

            case _:
                # AUTH_TYPE_NONE: No auth headers needed, just return default headers
                pass

        return headers

    def get_login_config(self) -> LoginConfig | None:
        """Get login configuration for custom auth if applicable.

        Returns:
            LoginConfig with login endpoint, method, payload template, etc.
            or None if not using login flow.
        """
        auth_config = self.auth_config

        if self.auth_type == AUTH_TYPE_CUSTOM and hasattr(auth_config, "login_endpoint") and auth_config.login_endpoint:
            return LoginConfig(
                login_endpoint=auth_config.login_endpoint,
                login_method=auth_config.login_method,
                login_payload_template=auth_config.login_payload_template,
                token_extraction=auth_config.token_extraction,
                extra_config=auth_config.extra_config,
                token_ttl_seconds=auth_config.extra_config.get("token_ttl_seconds", 1800),
            )
        return None

    def get_custom_request_headers(self) -> dict[str, str]:
        """Get static custom headers (without placeholder substitution).

        Returns:
            Dict of custom headers for non-login-flow custom auth.
        """
        auth_config = self.auth_config

        if self.auth_type == AUTH_TYPE_CUSTOM and hasattr(auth_config, "request_headers"):
            custom_headers = auth_config.request_headers
            if isinstance(custom_headers, dict):
                return {str(k): str(v) for k, v in custom_headers.items()}
        return {}

    @staticmethod
    def substitute_placeholders(template: Any, values: dict[str, Any]) -> Any:
        """Recursively substitute {placeholder} patterns in template with actual values.

        Example:
            template = {"user": "{username}", "nested": {"key": "{api_key}"}}
            values = {"username": "admin", "api_key": "secret123"}
            Result: {"user": "admin", "nested": {"key": "secret123"}}

        Args:
            template: Template with {placeholder} patterns (string, dict, or list)
            values: Dict of placeholder names to their replacement values

        Returns:
            Template with all placeholders replaced by their values
        """
        if isinstance(template, str):
            result = template
            for key, value in values.items():
                result = result.replace(f"{{{key}}}", str(value))
            return result
        elif isinstance(template, dict):
            return {k: ApiConnectorDomain.substitute_placeholders(v, values) for k, v in template.items()}
        elif isinstance(template, list):
            return [ApiConnectorDomain.substitute_placeholders(item, values) for item in template]
        return template

    @staticmethod
    def extract_value_by_path(data: dict | list, path: str) -> str:
        """Extract value from nested structure using dot-notation path.

        Examples:
            "Context.UserToken" -> data["Context"]["UserToken"]
            "data.token" -> data["data"]["token"]
            "items.0.id" -> data["items"][0]["id"]

        Args:
            data: Response data (dict or list)
            path: Dot-separated path to desired value

        Returns:
            Extracted value as string, or empty string if path invalid
        """
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    index = int(key)
                    current = current[index] if 0 <= index < len(current) else None
                except (ValueError, IndexError):
                    return ""
            else:
                return ""

            if current is None:
                return ""

        return str(current)

    def build_login_payload(self) -> dict[str, Any]:
        """Build login payload by substituting placeholders with extra_config values.

        Returns:
            Login payload with all placeholders replaced, or empty dict if not applicable.
        """
        login_config = self.get_login_config()
        if not login_config:
            return {}

        payload_template = login_config.login_payload_template
        extra_config = login_config.extra_config
        return self.substitute_placeholders(payload_template, extra_config)

    def extract_tokens_from_response(self, login_response: dict | list) -> dict[str, str]:
        """Extract session tokens from login response using configured extraction paths.

        Args:
            login_response: Parsed JSON response from login endpoint

        Returns:
            Dict of token_name -> token_value for all configured tokens

        Raises:
            ValidationError: If any configured token cannot be extracted
        """
        login_config = self.get_login_config()
        if not login_config:
            return {}

        token_extraction = login_config.token_extraction
        tokens: dict[str, str] = {}

        for token_name, extraction_path in token_extraction.items():
            token_value = self.extract_value_by_path(login_response, extraction_path)
            if not token_value:
                raise ValidationError(f"Failed to extract token '{token_name}' from path '{extraction_path}'")
            tokens[token_name] = token_value

        return tokens

    def build_custom_headers_with_tokens(self, tokens: dict[str, str]) -> dict[str, str]:
        """Build custom HTTP headers by substituting token placeholders with actual values.

        Args:
            tokens: Dict of token names to their actual values (from login response)

        Returns:
            Dict of HTTP headers with token placeholders replaced
        """
        auth_config = self.auth_config

        if hasattr(auth_config, "request_headers"):
            custom_headers = auth_config.request_headers
            if not isinstance(custom_headers, dict):
                return {}

            result: dict[str, str] = {}
            for key, value_template in custom_headers.items():
                header_value = str(value_template)
                # Replace {token_name} placeholders with actual token values
                for token_name, token_value in tokens.items():
                    header_value = header_value.replace(f"{{{token_name}}}", token_value)
                result[str(key)] = header_value

            return result
        return {}


@dataclass
class ApiOperationDomain(BaseDomainModel):
    """API operation domain model.

    Note: content_hash is used for detecting changes in API operation specs
    to determine if re-indexing is needed. This is separate from vector sync
    status tracking which is now managed via ResourceIndex.
    """

    id: int
    connector_id: int
    operation_uid: str
    method: str
    path_template: str
    operation_id: str | None
    summary: str
    description: str | None
    tags: list[str]
    request_schema: dict[str, Any] | None
    response_schema: dict[str, Any] | None
    auth_requirement: AuthRequirement
    risk_level: RiskLevel
    source: OperationSource
    upstream_key: str | None
    content_hash: str | None  # For detecting spec changes
    status: OperationStatus
    owner_id: int
    created_at: datetime
    updated_at: datetime
    # Vector sync status (from ResourceIndex)
    last_vector_synced_at: datetime | None = None
    last_vector_sync_error: str | None = None
    last_vector_sync_failed_at: datetime | None = None

    def to_searchable_text(self) -> str:
        """Build semantic/search text for vector indexing."""
        sections = [
            f"method: {self.method}",
            f"path: {self.path_template}",
        ]
        if self.operation_id:
            sections.append(f"operation_id: {self.operation_id}")
        if self.summary:
            sections.append(f"summary: {self.summary}")
        if self.description:
            sections.append(f"description: {self.description}")
        if self.tags:
            sections.append(f"tags: {' '.join(self.tags)}")
        return "\n".join(sections)
