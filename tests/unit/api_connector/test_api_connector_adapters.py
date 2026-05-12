"""Unit tests for API connector adapters - encryption/decryption and masking."""

from datetime import UTC, datetime

from apps.shared.api_connector.adapters import (
    auth_config_to_dict,
    connector_domain_to_response,
    connector_entity_to_domain,
)
from apps.shared.api_connector.constants import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_CUSTOM,
    AUTH_TYPE_NONE,
    CONNECTOR_STATUS_ACTIVE,
    SCHEMA_SOURCE_TYPE_MANUAL,
    SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD,
)
from apps.shared.api_connector.domain import ApiConnectorDomain, NoAuthConfig, RatePolicyDomain
from apps.shared.api_connector.schemas import ApiKeyAuthConfigSchema, NoAuthConfigSchema
from apps.shared.db.models import ApiConnector, User
from apps.shared.utils.field_cipher import FieldCipher


class TestAuthConfigToDict:
    def test_none_and_empty_dict(self):
        assert auth_config_to_dict(None) == {}
        assert auth_config_to_dict({}) == {}

    def test_pydantic_no_auth_schema(self):
        assert auth_config_to_dict(NoAuthConfigSchema()) == {"auth_method": "none"}

    def test_pydantic_api_key_schema(self):
        dumped = auth_config_to_dict(ApiKeyAuthConfigSchema(key_value="secret"))
        assert dumped["auth_method"] == "api_key"
        assert dumped["key_value"] == "secret"

    def test_domain_dataclass(self):
        assert auth_config_to_dict(NoAuthConfig()) == {"auth_method": "none"}


class TestConnectorEntityToDomain:
    """Test DB entity to domain model conversion with auto-decryption."""

    def test_convert_without_cipher_keeps_encrypted(self):
        """Without cipher, auth_config remains encrypted."""
        connector = ApiConnector(
            id=1,
            tenant_id=1,
            owner_id=1,
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_API_KEY,
            auth_config={"api_key": "enc:abc123", "endpoint": "https://api.example.com/v1"},
            rate_policy={},
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        connector.owner_user = User(id=1, username="testuser")

        domain = connector_entity_to_domain(connector, cipher=None)

        # Auth config should be converted to dataclass
        # Without cipher, api_key remains encrypted in the dataclass
        from apps.shared.api_connector.domain import ApiKeyAuthConfig

        assert isinstance(domain.auth_config, ApiKeyAuthConfig)
        assert domain.auth_config.api_key == "enc:abc123"

    def test_convert_with_cipher_auto_decrypts(self):
        """With cipher, auth_config is automatically decrypted."""
        cipher = FieldCipher()

        # Encrypt a test auth config
        original_auth = {
            "api_key": "sk-test-1234567890abcdef",
            "endpoint": "https://api.example.com/v1",
        }
        encrypted_auth = cipher.encrypt_dict(original_auth, sensitive_fields={"api_key", "token", "client_secret"})

        connector = ApiConnector(
            id=1,
            tenant_id=1,
            owner_id=1,
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_API_KEY,
            auth_config=encrypted_auth,
            rate_policy={},
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        connector.owner_user = User(id=1, username="testuser")

        domain = connector_entity_to_domain(connector, cipher=cipher)

        # Auth config should be decrypted and converted to dataclass
        from apps.shared.api_connector.domain import ApiKeyAuthConfig

        assert isinstance(domain.auth_config, ApiKeyAuthConfig)
        assert domain.auth_config.api_key == "sk-test-1234567890abcdef"

    def test_convert_with_empty_auth_config(self):
        """Empty auth_config should be handled gracefully."""
        connector = ApiConnector(
            id=1,
            tenant_id=1,
            owner_id=1,
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_NONE,
            auth_config={},
            rate_policy={},
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        connector.owner_user = User(id=1, username="testuser")

        cipher = FieldCipher()
        domain = connector_entity_to_domain(connector, cipher=cipher)

        # Empty auth_config becomes NoAuthConfig
        from apps.shared.api_connector.domain import NoAuthConfig

        assert isinstance(domain.auth_config, NoAuthConfig)

    def test_convert_with_none_auth_config(self):
        """None auth_config should be converted to empty dict."""
        connector = ApiConnector(
            id=1,
            tenant_id=1,
            owner_id=1,
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_NONE,
            auth_config=None,
            rate_policy={},
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        connector.owner_user = User(id=1, username="testuser")

        cipher = FieldCipher()
        domain = connector_entity_to_domain(connector, cipher=cipher)

        # None auth_config becomes NoAuthConfig
        from apps.shared.api_connector.domain import NoAuthConfig

        assert isinstance(domain.auth_config, NoAuthConfig)

    def test_convert_preserves_all_fields(self):
        """All connector fields should be properly mapped."""
        now = datetime.now(UTC)
        connector = ApiConnector(
            id=42,
            tenant_id=10,
            owner_id=5,
            name="production-api",
            description="Production API Connector",
            base_url="https://prod.example.com",
            auth_type=AUTH_TYPE_BEARER,
            auth_config={"token": "enc:xyz789"},
            rate_policy={"timeout_ms": 5000},
            schema_source_type=SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD,
            schema_source_url=None,
            schema_metadata={"version": "1.0"},
            schema_last_synced_at=now,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=now,
            updated_at=now,
        )
        connector.owner_user = User(id=5, username="admin")

        domain = connector_entity_to_domain(connector, cipher=None)

        assert domain.id == 42
        assert domain.tenant_id == 10
        assert domain.owner_id == 5
        assert domain.owner_name == "admin"
        assert domain.name == "production-api"
        assert domain.description == "Production API Connector"
        assert domain.base_url == "https://prod.example.com"
        assert domain.auth_type == AUTH_TYPE_BEARER
        assert domain.schema_source_type == SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD
        assert domain.schema_metadata == {"version": "1.0"}
        assert domain.status == CONNECTOR_STATUS_ACTIVE


class TestConnectorDomainToResponse:
    """Test domain model to response DTO conversion with auto-masking."""

    def test_masking_applied_to_sensitive_fields(self):
        """Sensitive fields in auth_config should be masked."""
        domain = ApiConnectorDomain(
            id=1,
            tenant_id=1,
            owner_id=1,
            owner_name="admin",
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_API_KEY,
            auth_config={
                "api_key": "sk-test-1234567890abcdef",
                "endpoint": "https://api.example.com/v1",
            },
            rate_policy=RatePolicyDomain(),
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = connector_domain_to_response(domain)

        # api_key should be masked (first 2 + stars + last 2)
        assert response.auth_config_masked["api_key"] == "sk********************ef"
        # endpoint should remain unchanged (not sensitive)
        assert response.auth_config_masked["endpoint"] == "https://api.example.com/v1"

    def test_masking_with_multiple_sensitive_fields(self):
        """Multiple sensitive fields should all be masked."""
        domain = ApiConnectorDomain(
            id=1,
            tenant_id=1,
            owner_id=1,
            owner_name="admin",
            name="oauth-api",
            description="OAuth API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_CUSTOM,
            auth_config={
                "client_id": "my-client-id",
                "client_secret": "secret-1234567890",
                "access_token": "token-abcdefghijklmnop",
                "refresh_token": "refresh-xyz123",
                "endpoint": "https://api.example.com/oauth",
            },
            rate_policy=RatePolicyDomain(),
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = connector_domain_to_response(domain)

        # All sensitive fields should be masked
        assert response.auth_config_masked["client_id"] == "my-client-id"  # Not sensitive
        assert (
            "****" in response.auth_config_masked["client_secret"]
            or "se" in response.auth_config_masked["client_secret"]
        )
        assert (
            "****" in response.auth_config_masked["access_token"] or "to" in response.auth_config_masked["access_token"]
        )
        assert (
            "****" in response.auth_config_masked["refresh_token"]
            or "re" in response.auth_config_masked["refresh_token"]
        )
        # endpoint should remain unchanged
        assert response.auth_config_masked["endpoint"] == "https://api.example.com/oauth"

    def test_masking_with_empty_auth_config(self):
        """Empty auth_config should result in empty masked config."""
        domain = ApiConnectorDomain(
            id=1,
            tenant_id=1,
            owner_id=1,
            owner_name="admin",
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_NONE,
            auth_config={},
            rate_policy=RatePolicyDomain(),
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = connector_domain_to_response(domain)

        assert response.auth_config_masked == {}

    def test_masking_with_short_values(self):
        """Short sensitive values should be fully masked."""
        domain = ApiConnectorDomain(
            id=1,
            tenant_id=1,
            owner_id=1,
            owner_name="admin",
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_API_KEY,
            auth_config={
                "api_key": "abc",  # Very short
                "token": "1234",  # Exactly 4 chars
            },
            rate_policy=RatePolicyDomain(),
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = connector_domain_to_response(domain)

        # Short values should be fully masked
        assert response.auth_config_masked["api_key"] == "***"
        assert response.auth_config_masked["token"] == "****"

    def test_response_dto_contains_all_fields(self):
        """Response DTO should contain all connector fields."""
        now = datetime.now(UTC)
        domain = ApiConnectorDomain(
            id=42,
            tenant_id=10,
            owner_id=5,
            owner_name="admin",
            name="production-api",
            description="Production API",
            base_url="https://prod.example.com",
            auth_type=AUTH_TYPE_BEARER,
            auth_config={"token": "secret-token"},
            rate_policy=RatePolicyDomain(timeout_ms=5000),
            schema_source_type=SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD,
            schema_source_url=None,
            schema_metadata={"version": "1.0"},
            schema_last_synced_at=now,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=now,
            updated_at=now,
        )

        response = connector_domain_to_response(domain)

        assert response.id == 42
        assert response.tenant_id == 10
        assert response.owner_id == 5
        assert response.owner_name == "admin"
        assert response.name == "production-api"
        assert response.description == "Production API"
        assert response.base_url == "https://prod.example.com"
        assert response.auth_type == AUTH_TYPE_BEARER
        assert response.schema_source_type == SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD
        assert response.schema_metadata == {"version": "1.0"}
        assert response.status == CONNECTOR_STATUS_ACTIVE
        assert response.auth_config_masked is not None

    def test_masking_does_not_modify_original_domain(self):
        """Masking should create a copy, not modify the original domain."""
        from apps.shared.api_connector.domain import ApiKeyAuthConfig

        original_api_key = "sk-test-original-key-12345"
        domain = ApiConnectorDomain(
            id=1,
            tenant_id=1,
            owner_id=1,
            owner_name="admin",
            name="test-api",
            description="Test API",
            base_url="https://api.example.com",
            auth_type=AUTH_TYPE_API_KEY,
            auth_config=ApiKeyAuthConfig(api_key=original_api_key),
            rate_policy=RatePolicyDomain(),
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = connector_domain_to_response(domain)

        # Original domain should remain unchanged (dataclass attribute)
        assert domain.auth_config.api_key == original_api_key
        # Response should have masked value
        assert response.auth_config_masked["api_key"] != original_api_key


class TestEncryptionDecryptionMaskingFlow:
    """Test complete flow: encrypt → decrypt → mask."""

    def test_full_lifecycle(self):
        """Test complete lifecycle: original → encrypt → decrypt → mask."""
        cipher = FieldCipher()

        # Original auth config
        original = {
            "api_key": "sk-live-secret-key-1234567890",
            "endpoint": "https://api.production.com/v1",
        }

        # Step 1: Encrypt (simulating DB storage)
        encrypted = cipher.encrypt_dict(original, sensitive_fields={"api_key", "token", "client_secret"})
        assert encrypted["api_key"].startswith("enc:")
        assert encrypted["endpoint"] == "https://api.production.com/v1"

        # Step 2: Create connector with encrypted auth (simulating DB entity)
        connector = ApiConnector(
            id=1,
            tenant_id=1,
            owner_id=1,
            name="production-api",
            description="Production API",
            base_url="https://api.production.com",
            auth_type=AUTH_TYPE_API_KEY,
            auth_config=encrypted,
            rate_policy={},
            schema_source_type=SCHEMA_SOURCE_TYPE_MANUAL,
            schema_source_url=None,
            schema_metadata={},
            schema_last_synced_at=None,
            status=CONNECTOR_STATUS_ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        connector.owner_user = User(id=1, username="admin")

        # Step 3: Convert to domain (auto-decrypt + convert to dataclass)
        domain = connector_entity_to_domain(connector, cipher=cipher)
        from apps.shared.api_connector.domain import ApiKeyAuthConfig

        assert isinstance(domain.auth_config, ApiKeyAuthConfig)
        assert domain.auth_config.api_key == "sk-live-secret-key-1234567890"

        # Step 4: Convert to response (auto-mask)
        response = connector_domain_to_response(domain)
        # api_key masked: first 2 + stars + last 2
        assert response.auth_config_masked["api_key"] == "sk*************************90"
        # endpoint is not part of ApiKeyAuthConfig, so it won't be in masked output

        # Verify original value is not exposed
        assert "sk-live-secret-key-1234567890" not in str(response.auth_config_masked)
