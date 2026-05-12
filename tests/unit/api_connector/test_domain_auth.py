"""Unit tests for ApiConnectorDomain authentication header building methods."""

from __future__ import annotations

import base64

import pytest

from apps.shared.api_connector.domain import (
    ApiConnectorDomain,
    ApiKeyAuthConfig,
    BasicAuthConfig,
    BearerAuthConfig,
    CustomAuthConfig,
    NoAuthConfig,
    RatePolicyDomain,
)
from apps.shared.core.exceptions import ValidationError


def _dict_to_auth_config(auth_type: str, auth_dict: dict):
    """Convert dict to typed auth config dataclass for tests."""
    match auth_type:
        case "api_key":
            return ApiKeyAuthConfig(**auth_dict)
        case "bearer":
            return BearerAuthConfig(**auth_dict)
        case "basic":
            return BasicAuthConfig(**auth_dict)
        case "custom":
            return CustomAuthConfig(**auth_dict)
        case _:
            return NoAuthConfig()


def create_connector_domain(
    auth_type: str,
    auth_config: dict,
    **overrides,
) -> ApiConnectorDomain:
    """Factory to create ApiConnectorDomain for testing."""
    # Convert dict to typed dataclass
    typed_auth_config = _dict_to_auth_config(auth_type, auth_config)

    defaults = dict(
        id=1,
        tenant_id=1,
        owner_id=1,
        name="test-connector",
        description=None,
        base_url="https://api.example.com",
        auth_type=auth_type,
        auth_config=typed_auth_config,
        rate_policy=RatePolicyDomain(),
        schema_source_type="manual",
        schema_source_url=None,
        schema_metadata={},
        schema_last_synced_at=None,
        status="active",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        owner_name="test-user",
    )
    defaults.update(overrides)
    return ApiConnectorDomain(**defaults)


class TestBuildHeaders:
    """Tests for ApiConnectorDomain.build_headers() method."""

    # ==================== Happy Path Tests ====================

    def test_api_key_auth_returns_correct_header(self):
        """API key auth should set the key in specified header."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_name": "X-API-Key", "key_value": "secret-key-12345"},
        )

        headers = connector.build_headers()

        assert headers["User-Agent"] == "LingQing-ApiConnector/1.0"
        assert headers["X-API-Key"] == "secret-key-12345"

    def test_api_key_auth_uses_default_header_name(self):
        """API key auth should use X-API-Key if key_name not specified."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": "my-secret-key"},
        )

        headers = connector.build_headers()

        assert headers["X-API-Key"] == "my-secret-key"

    def test_api_key_auth_accepts_api_key_field(self):
        """API key auth should also accept 'api_key' field."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"api_key": "fallback-key-field"},
        )

        headers = connector.build_headers()

        assert headers["X-API-Key"] == "fallback-key-field"

    def test_bearer_auth_returns_authorization_header(self):
        """Bearer auth should set Authorization header with Bearer token."""
        connector = create_connector_domain(
            auth_type="bearer",
            auth_config={"token": "bearer-token-xyz"},
        )

        headers = connector.build_headers()

        assert headers["Authorization"] == "Bearer bearer-token-xyz"

    def test_bearer_auth_accepts_access_token_field(self):
        """Bearer auth should also accept 'access_token' field."""
        connector = create_connector_domain(
            auth_type="bearer",
            auth_config={"access_token": "oauth-access-token"},
        )

        headers = connector.build_headers()

        assert headers["Authorization"] == "Bearer oauth-access-token"

    def test_basic_auth_returns_encoded_credentials(self):
        """Basic auth should encode username:password in Authorization header."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={"username": "admin", "password": "secret123"},
        )

        headers = connector.build_headers()

        expected = f"Basic {base64.b64encode(b'admin:secret123').decode('utf-8')}"
        assert headers["Authorization"] == expected

    def test_none_auth_returns_only_default_headers(self):
        """No auth should return only default headers (User-Agent)."""
        connector = create_connector_domain(
            auth_type="none",
            auth_config={},
        )

        headers = connector.build_headers()

        assert headers == {"User-Agent": "LingQing-ApiConnector/1.0"}

    def test_extra_headers_are_added(self):
        """Extra headers should be merged into result."""
        connector = create_connector_domain(
            auth_type="none",
            auth_config={},
        )

        headers = connector.build_headers(extra_headers={"X-Custom": "value", "Authorization": "override"})

        assert headers["User-Agent"] == "LingQing-ApiConnector/1.0"
        assert headers["X-Custom"] == "value"
        assert headers["Authorization"] == "override"  # Extra headers can override default

    # ==================== Validation Error Tests ====================

    def test_api_key_missing_key_value_raises(self):
        """API key auth with missing key_value should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={},  # No key_value or api_key
        )

        with pytest.raises(ValidationError, match="Missing api_key/key_value"):
            connector.build_headers()

    def test_bearer_missing_token_raises(self):
        """Bearer auth with missing token should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="bearer",
            auth_config={},  # No token or access_token
        )

        with pytest.raises(ValidationError, match="Missing bearer token"):
            connector.build_headers()

    def test_basic_missing_username_raises(self):
        """Basic auth with missing username should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={"password": "secret"},
        )

        with pytest.raises(ValidationError, match="Missing username/password"):
            connector.build_headers()

    def test_basic_missing_password_raises(self):
        """Basic auth with missing password should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={"username": "admin"},
        )

        with pytest.raises(ValidationError, match="Missing username/password"):
            connector.build_headers()

    def test_basic_missing_both_raises(self):
        """Basic auth with missing both username and password should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={},
        )

        with pytest.raises(ValidationError, match="Missing username/password"):
            connector.build_headers()

    # ==================== Edge Cases ====================

    def test_api_key_empty_string_key_value_raises(self):
        """API key auth with empty string key_value should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": ""},
        )

        with pytest.raises(ValidationError, match="Missing api_key/key_value"):
            connector.build_headers()

    def test_bearer_empty_string_token_raises(self):
        """Bearer auth with empty string token should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="bearer",
            auth_config={"token": ""},
        )

        with pytest.raises(ValidationError, match="Missing bearer token"):
            connector.build_headers()

    def test_basic_empty_credentials_raises(self):
        """Basic auth with empty credentials should raise ValidationError."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={"username": "", "password": ""},
        )

        with pytest.raises(ValidationError, match="Missing username/password"):
            connector.build_headers()

    def test_special_characters_in_credentials_are_encoded(self):
        """Special characters in credentials should be handled correctly."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={"username": "user@example.com", "password": "p@ssw0rd!"},
        )

        headers = connector.build_headers()
        expected = f"Basic {base64.b64encode(b'user@example.com:p@ssw0rd!').decode('utf-8')}"
        assert headers["Authorization"] == expected

    def test_unicode_credentials_are_encoded(self):
        """Unicode characters in credentials should be UTF-8 encoded."""
        connector = create_connector_domain(
            auth_type="basic",
            auth_config={"username": "用户", "password": "密码"},
        )

        headers = connector.build_headers()
        expected = f"Basic {base64.b64encode('用户:密码'.encode('utf-8')).decode('utf-8')}"
        assert headers["Authorization"] == expected

    def test_custom_auth_returns_static_headers_only(self):
        """Custom auth without login_endpoint returns static headers (no token substitution)."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "request_headers": {
                    "X-Session-Id": "static-session-id",
                    "X-Request-Id": "request-123",
                }
            },
        )

        headers = connector.build_headers()

        assert headers["User-Agent"] == "LingQing-ApiConnector/1.0"
        assert headers["X-Session-Id"] == "static-session-id"
        assert headers["X-Request-Id"] == "request-123"

    def test_custom_auth_empty_headers(self):
        """Custom auth with no request_headers returns only default headers."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={},
        )

        headers = connector.build_headers()

        assert headers == {"User-Agent": "LingQing-ApiConnector/1.0"}

    def test_unknown_auth_type_returns_default_headers(self):
        """Unknown auth type should return default headers without error."""
        connector = create_connector_domain(
            auth_type="unknown_type",
            auth_config={},
        )

        headers = connector.build_headers()

        # Unknown auth type doesn't match any condition, so just returns defaults
        assert headers == {"User-Agent": "LingQing-ApiConnector/1.0"}


class TestGetLoginConfig:
    """Tests for ApiConnectorDomain.get_login_config() method."""

    def test_custom_auth_with_login_returns_config(self):
        """Custom auth with login_endpoint should return login configuration."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth/login",
                "login_method": "POST",
                "login_payload_template": {"user": "{username}", "pass": "{password}"},
                "token_extraction": {"token": "data.token", "session": "data.sessionId"},
                "extra_config": {"username": "admin", "password": "secret", "token_ttl_seconds": 3600},
            },
        )

        config = connector.get_login_config()

        assert config is not None
        assert config.login_endpoint == "/auth/login"
        assert config.login_method == "POST"
        assert config.login_payload_template == {"user": "{username}", "pass": "{password}"}
        assert config.token_extraction == {"token": "data.token", "session": "data.sessionId"}
        assert config.extra_config == {"username": "admin", "password": "secret", "token_ttl_seconds": 3600}
        assert config.token_ttl_seconds == 3600

    def test_custom_auth_without_login_returns_none(self):
        """Custom auth without login_endpoint should return None."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={"request_headers": {"X-Custom": "value"}},
        )

        config = connector.get_login_config()

        assert config is None

    def test_non_custom_auth_returns_none(self):
        """Non-custom auth types should return None even if they have similar config."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": "secret"},
        )

        config = connector.get_login_config()

        assert config is None

    def test_custom_auth_defaults_login_method(self):
        """Custom auth should default login_method to POST if not specified."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth/login",
                "login_payload_template": {},
                "extra_config": {"token_ttl_seconds": 1800},
            },
        )

        config = connector.get_login_config()

        assert config is not None
        assert config.login_method == "POST"

    def test_custom_auth_defaults_token_ttl(self):
        """Custom auth should default token_ttl_seconds to 1800 if not specified."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth/login",
                "extra_config": {},
            },
        )

        config = connector.get_login_config()

        assert config is not None
        assert config.token_ttl_seconds == 1800

    def test_custom_auth_with_nested_extra_config(self):
        """Custom auth should handle nested extra_config (flat structure)."""
        # Note: token_ttl_seconds is expected to be at extra_config root level
        # Nested paths like extra_config.nested.token_ttl_seconds are not supported
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/api/auth",
                "extra_config": {
                    "username": "user",
                    "nested": {"some_data": "value"},  # Additional nested data preserved
                },
            },
        )

        config = connector.get_login_config()

        assert config is not None
        assert config.extra_config == {
            "username": "user",
            "nested": {"some_data": "value"},
        }
        # Falls back to default 1800 when token_ttl_seconds not at root level
        assert config.token_ttl_seconds == 1800


class TestGetCustomRequestHeaders:
    """Tests for ApiConnectorDomain.get_custom_request_headers() method."""

    def test_custom_auth_returns_headers(self):
        """Custom auth should return request_headers dict."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "request_headers": {
                    "X-Session-Id": "session-123",
                    "X-Custom-Header": "custom-value",
                }
            },
        )

        headers = connector.get_custom_request_headers()

        assert headers == {
            "X-Session-Id": "session-123",
            "X-Custom-Header": "custom-value",
        }

    def test_custom_auth_empty_returns_empty_dict(self):
        """Custom auth with no request_headers returns empty dict."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={},
        )

        headers = connector.get_custom_request_headers()

        assert headers == {}

    def test_non_custom_auth_returns_empty_dict(self):
        """Non-custom auth types return empty dict regardless of their config."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": "secret"},
        )

        headers = connector.get_custom_request_headers()

        assert headers == {}

    def test_headers_are_string_converted(self):
        """Non-string header values should be converted to strings."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "request_headers": {
                    "X-Number": 123,
                    "X-Boolean": True,
                    "X-String": "value",
                }
            },
        )

        headers = connector.get_custom_request_headers()

        assert headers["X-Number"] == "123"
        assert headers["X-Boolean"] == "True"
        assert headers["X-String"] == "value"


class TestHeaderBuildWithTypedAuthConfig:
    """Tests for domain methods using typed AuthConfig (Pydantic models)."""

    def test_build_headers_with_dict_auth_config(self):
        """build_headers should work with dict auth_config (legacy/compatibility)."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": "dict-based-key"},
        )

        headers = connector.build_headers()

        assert headers["X-API-Key"] == "dict-based-key"

    def test_get_login_config_with_dict_auth_config(self):
        """get_login_config should work with dict auth_config."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/login",
                "extra_config": {"token_ttl_seconds": 600},
            },
        )

        config = connector.get_login_config()

        assert config is not None
        assert config.token_ttl_seconds == 600

    def test_get_custom_request_headers_with_dict_auth_config(self):
        """get_custom_request_headers should work with dict auth_config."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "request_headers": {"X-Key": "value"},
            },
        )

        headers = connector.get_custom_request_headers()

        assert headers == {"X-Key": "value"}


class TestDomainUtilityMethods:
    """Tests for static utility methods in ApiConnectorDomain."""

    def test_substitute_placeholders_simple_string(self):
        """Should replace placeholders in simple string."""
        result = ApiConnectorDomain.substitute_placeholders(
            "Hello {username}, your key is {api_key}",
            {"username": "admin", "api_key": "secret123"},
        )

        assert result == "Hello admin, your key is secret123"

    def test_substitute_placeholders_dict(self):
        """Should replace placeholders in nested dict."""
        template = {
            "user": "{username}",
            "nested": {"key": "{api_key}", "deep": {"value": "{secret}"}},
        }
        values = {"username": "admin", "api_key": "key123", "secret": "mysecret"}

        result = ApiConnectorDomain.substitute_placeholders(template, values)

        assert result["user"] == "admin"
        assert result["nested"]["key"] == "key123"
        assert result["nested"]["deep"]["value"] == "mysecret"

    def test_substitute_placeholders_list(self):
        """Should replace placeholders in list."""
        template = ["{username}", "{password}", "static"]
        values = {"username": "admin", "password": "pass123"}

        result = ApiConnectorDomain.substitute_placeholders(template, values)

        assert result == ["admin", "pass123", "static"]

    def test_substitute_placeholders_mixed_types(self):
        """Should handle mixed types in template."""
        template = {
            "string": "{value}",
            "number": 42,
            "bool": True,
            "none": None,
            "nested": ["{item1}", "{item2}"],
        }
        values = {"value": "test", "item1": "a", "item2": "b"}

        result = ApiConnectorDomain.substitute_placeholders(template, values)

        assert result["string"] == "test"
        assert result["number"] == 42
        assert result["bool"] is True
        assert result["none"] is None
        assert result["nested"] == ["a", "b"]

    def test_substitute_placeholders_missing_values(self):
        """Should leave placeholders unchanged if value not provided."""
        result = ApiConnectorDomain.substitute_placeholders(
            "{username} {missing}",
            {"username": "admin"},
        )

        assert result == "admin {missing}"

    def test_extract_value_by_path_simple(self):
        """Should extract value using simple dot path."""
        data = {"user": {"token": "abc123", "session": "xyz"}, "other": "other_data"}

        assert ApiConnectorDomain.extract_value_by_path(data, "other") == "other_data"
        assert ApiConnectorDomain.extract_value_by_path(data, "user.token") == "abc123"
        assert ApiConnectorDomain.extract_value_by_path(data, "user.session") == "xyz"

    def test_extract_value_by_path_nested(self):
        """Should extract value from deeply nested structure."""
        data = {
            "Context": {
                "UserToken": "token-123",
                "SessionId": "session-456",
            }
        }

        assert ApiConnectorDomain.extract_value_by_path(data, "Context.UserToken") == "token-123"
        assert ApiConnectorDomain.extract_value_by_path(data, "Context.SessionId") == "session-456"

    def test_extract_value_by_path_with_array(self):
        """Should handle array indices in path."""
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}

        assert ApiConnectorDomain.extract_value_by_path(data, "items.0.id") == "1"
        assert ApiConnectorDomain.extract_value_by_path(data, "items.2.id") == "3"

    def test_extract_value_by_path_invalid_path(self):
        """Should return empty string for invalid paths."""
        data = {"user": "admin"}

        assert ApiConnectorDomain.extract_value_by_path(data, "missing.field") == ""
        assert ApiConnectorDomain.extract_value_by_path(data, "user.invalid") == ""

    def test_extract_value_by_path_array_out_of_bounds(self):
        """Should return empty string for out-of-bounds array index."""
        data = {"items": ["a", "b"]}

        assert ApiConnectorDomain.extract_value_by_path(data, "items.5") == ""

    def test_extract_value_by_path_non_integer_array_index(self):
        """Should return empty string for non-integer array index."""
        data = {"items": ["a", "b"]}

        assert ApiConnectorDomain.extract_value_by_path(data, "items.invalid") == ""


class TestDomainAuthProcessingMethods:
    """Tests for ApiConnectorDomain authentication processing methods."""

    def test_build_login_payload(self):
        """Should build login payload with placeholders substituted."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth/login",
                "login_method": "POST",
                "login_payload_template": {
                    "username": "{username}",
                    "password": "{password}",
                    "api_key": "{api_key}",
                },
                "extra_config": {
                    "username": "admin",
                    "password": "secret123",
                    "api_key": "key-abc",
                },
            },
        )

        payload = connector.build_login_payload()

        assert payload == {
            "username": "admin",
            "password": "secret123",
            "api_key": "key-abc",
        }

    def test_build_login_payload_no_login_config(self):
        """Should return empty dict if no login config."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": "secret"},
        )

        payload = connector.build_login_payload()

        assert payload == {}

    def test_build_login_payload_nested_template(self):
        """Should handle nested payload templates."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth",
                "login_payload_template": {
                    "credentials": {
                        "user": "{username}",
                        "pass": "{password}",
                    },
                    "metadata": {"source": "api"},
                },
                "extra_config": {
                    "username": "admin",
                    "password": "pass",
                },
            },
        )

        payload = connector.build_login_payload()

        assert payload["credentials"]["user"] == "admin"
        assert payload["credentials"]["pass"] == "pass"
        assert payload["metadata"]["source"] == "api"

    def test_extract_tokens_from_response(self):
        """Should extract tokens from login response."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth",
                "token_extraction": {
                    "user_token": "Context.UserToken",
                    "session_id": "Context.SessionId",
                },
                "extra_config": {},
            },
        )

        login_response = {
            "Context": {
                "UserToken": "token-123",
                "SessionId": "session-456",
            }
        }

        tokens = connector.extract_tokens_from_response(login_response)

        assert tokens["user_token"] == "token-123"
        assert tokens["session_id"] == "session-456"

    def test_extract_tokens_from_response_missing_token(self):
        """Should raise ValidationError if token cannot be extracted."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth",
                "token_extraction": {
                    "token": "data.token",
                },
                "extra_config": {},
            },
        )

        login_response = {"data": {"other": "value"}}

        with pytest.raises(ValidationError, match="Failed to extract token 'token'"):
            connector.extract_tokens_from_response(login_response)

    def test_extract_tokens_from_response_no_login_config(self):
        """Should return empty dict if no login config."""
        connector = create_connector_domain(
            auth_type="api_key",
            auth_config={"key_value": "secret"},
        )

        tokens = connector.extract_tokens_from_response({})

        assert tokens == {}

    def test_build_custom_headers_with_tokens(self):
        """Should build headers with token placeholders substituted."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth",
                "request_headers": {
                    "X-User-Token": "{user_token}",
                    "X-Session-Id": "{session_id}",
                    "X-Static": "static-value",
                },
                "extra_config": {},
            },
        )

        tokens = {"user_token": "token-123", "session_id": "session-456"}
        headers = connector.build_custom_headers_with_tokens(tokens)

        assert headers == {
            "X-User-Token": "token-123",
            "X-Session-Id": "session-456",
            "X-Static": "static-value",
        }

    def test_build_custom_headers_with_tokens_multiple_replacements(self):
        """Should handle multiple token references in single header."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth",
                "request_headers": {
                    "Authorization": "Bearer {user_token} Session:{session_id}",
                },
                "extra_config": {},
            },
        )

        tokens = {"user_token": "token-123", "session_id": "session-456"}
        headers = connector.build_custom_headers_with_tokens(tokens)

        assert headers["Authorization"] == "Bearer token-123 Session:session-456"

    def test_build_custom_headers_with_tokens_no_custom_headers(self):
        """Should return empty dict if no request_headers configured."""
        connector = create_connector_domain(
            auth_type="custom",
            auth_config={
                "login_endpoint": "/auth",
                "extra_config": {},
            },
        )

        headers = connector.build_custom_headers_with_tokens({"token": "value"})

        assert headers == {}
