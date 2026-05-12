"""Integration tests for real-world API connector scenarios (Kingdee ERP, etc.)."""

from apps.shared.api_connector.domain import (
    ApiConnectorDomain,
    CustomAuthConfig,
    RatePolicyDomain,
)


def create_kingdee_connector(auth_config_dict: dict) -> ApiConnectorDomain:
    """Factory to create Kingdee connector with typed auth config."""
    return ApiConnectorDomain(
        id=1,
        tenant_id=1,
        owner_id=1,
        name="Kingdee ERP",
        description=None,
        base_url="https://erp.kingdee.com",
        auth_type="custom",
        auth_config=CustomAuthConfig(**auth_config_dict),
        rate_policy=RatePolicyDomain(),
        schema_source_type="manual",
        schema_source_url=None,
        schema_metadata={},
        schema_last_synced_at=None,
        status="active",
        created_at=None,
        updated_at=None,
    )


class TestKingdeeERPAuthFlow:
    """Tests for Kingdee ERP custom authentication flow.

    Kingdee uses a login-based auth pattern:
    1. POST to login endpoint with app credentials
    2. Extract UserToken and SessionId from response
    3. Use tokens in subsequent API requests via custom headers
    """

    def test_kingdee_login_payload_construction(self):
        """Kingdee login payload should substitute placeholders with credentials."""
        connector = create_kingdee_connector(
            {
                "auth_method": "custom",
                "login_endpoint": "/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc",
                "login_method": "POST",
                "login_payload_template": {
                    "parameters": ["{account_id}", "{username}", "{app_key}", "{app_secret}", 2052]
                },
                "token_extraction": {
                    "token": "Context.UserToken",
                    "session_id": "Context.SessionId",
                },
                "request_headers": {
                    "X-User-Token": "{token}",
                    "X-Session-Id": "{session_id}",
                    "Content-Type": "application/json",
                },
                "extra_config": {
                    "account_id": "datacenter-123",
                    "username": "admin",
                    "app_key": "my-app-key",
                    "app_secret": "encrypted-secret-value",
                    "token_ttl_seconds": 3600,
                },
            }
        )

        # Build login payload
        payload = connector.build_login_payload()

        assert payload == {"parameters": ["datacenter-123", "admin", "my-app-key", "encrypted-secret-value", 2052]}

    def test_kingdee_token_extraction_from_response(self):
        """Kingdee login response should extract tokens using dot-notation paths."""
        connector = create_kingdee_connector(
            {
                "auth_method": "custom",
                "login_endpoint": "/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc",
                "token_extraction": {
                    "token": "Context.UserToken",
                    "session_id": "Context.SessionId",
                },
                "extra_config": {},
            }
        )

        # Simulate Kingdee login response
        login_response = {
            "ResponseStatus": {
                "ErrorCode": 0,
                "IsSuccess": True,
                "Errors": [],
            },
            "Context": {
                "UserToken": "kingdee-token-abc123",
                "SessionId": "session-xyz789",
                "UserId": 10001,
                "UserName": "admin",
            },
        }

        tokens = connector.extract_tokens_from_response(login_response)

        assert tokens == {
            "token": "kingdee-token-abc123",
            "session_id": "session-xyz789",
        }

    def test_kingdee_custom_headers_with_tokens(self):
        """Kingdee API requests should include token-substituted headers."""
        connector = create_kingdee_connector(
            {
                "auth_method": "custom",
                "login_endpoint": "/auth/login",
                "request_headers": {
                    "X-User-Token": "{token}",
                    "X-Session-Id": "{session_id}",
                    "Content-Type": "application/json",
                },
                "extra_config": {},
            }
        )

        # Simulate extracted tokens
        tokens = {
            "token": "kingdee-token-abc123",
            "session_id": "session-xyz789",
        }

        headers = connector.build_custom_headers_with_tokens(tokens)

        assert headers == {
            "X-User-Token": "kingdee-token-abc123",
            "X-Session-Id": "session-xyz789",
            "Content-Type": "application/json",
        }

    def test_kingdee_full_auth_flow_simulation(self):
        """Simulate complete Kingdee auth flow: payload → tokens → headers."""
        connector = create_kingdee_connector(
            {
                "auth_method": "custom",
                "login_endpoint": "/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc",
                "login_method": "POST",
                "login_payload_template": {
                    "parameters": ["{account_id}", "{username}", "{app_key}", "{app_secret}", 2052]
                },
                "token_extraction": {
                    "token": "Context.UserToken",
                    "session_id": "Context.SessionId",
                },
                "request_headers": {
                    "X-User-Token": "{token}",
                    "X-Session-Id": "{session_id}",
                    "Content-Type": "application/json",
                },
                "extra_config": {
                    "account_id": "datacenter-123",
                    "username": "admin",
                    "app_key": "my-app-key",
                    "app_secret": "secret-xyz",
                },
            }
        )

        # Step 1: Build login payload
        login_payload = connector.build_login_payload()
        assert login_payload["parameters"][0] == "datacenter-123"
        assert login_payload["parameters"][1] == "admin"

        # Step 2: Simulate login response and extract tokens
        mock_login_response = {
            "Context": {
                "UserToken": "real-token-from-kingdee",
                "SessionId": "real-session-id",
            }
        }
        tokens = connector.extract_tokens_from_response(mock_login_response)
        assert tokens["token"] == "real-token-from-kingdee"
        assert tokens["session_id"] == "real-session-id"

        # Step 3: Build API request headers with tokens
        api_headers = connector.build_custom_headers_with_tokens(tokens)
        assert api_headers["X-User-Token"] == "real-token-from-kingdee"
        assert api_headers["X-Session-Id"] == "real-session-id"
        assert api_headers["Content-Type"] == "application/json"

    def test_kingdee_login_config_extraction(self):
        """Kingdee login config should be properly extracted from auth_config."""
        connector = create_kingdee_connector(
            {
                "auth_method": "custom",
                "login_endpoint": "/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc",
                "login_method": "POST",
                "extra_config": {
                    "token_ttl_seconds": 7200,  # 2 hours
                },
            }
        )

        login_config = connector.get_login_config()

        assert login_config is not None
        assert (
            login_config.login_endpoint == "/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc"
        )
        assert login_config.login_method == "POST"
        assert login_config.token_ttl_seconds == 7200
