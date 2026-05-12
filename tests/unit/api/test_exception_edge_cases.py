"""Additional test for exception handler edge cases."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.exceptions import DomainException


@pytest.fixture
def app():
    """Create a test FastAPI app with exception handlers."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/test-custom-domain")
    async def test_custom_domain():
        # Test a custom domain exception that doesn't have specific handler
        class CustomDomainError(DomainException):
            """Custom domain exception."""

            pass

        raise CustomDomainError("Custom domain error")

    @app.get("/test-base-domain")
    async def test_base_domain():
        raise DomainException("Base domain error")

    @app.get("/test-unexpected")
    async def test_unexpected():
        # Simulate an unexpected exception (not a DomainException)
        raise ValueError("Unexpected ValueError from third-party lib")

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


def test_custom_domain_exception_handler(client):
    """Test that custom DomainException subclasses are caught by base handler."""
    response = client.get("/test-custom-domain")
    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "DOMAIN_ERROR"
    assert payload["message"] == "Internal server error"
    assert payload["details"]["exception_type"] == "CustomDomainError"
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_base_domain_exception_handler(client):
    """Test that base DomainException is caught."""
    response = client.get("/test-base-domain")
    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "DOMAIN_ERROR"
    assert payload["message"] == "Internal server error"
    assert payload["details"]["exception_type"] == "DomainException"
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_unexpected_exception_handler(client):
    """Test that unexpected exceptions (non-domain) are caught by Exception handler."""
    # TestClient in raise_server_exceptions=True mode (default) will re-raise server errors
    # We need to configure it to not raise to properly test the handler
    from starlette.testclient import TestClient as StarletteTestClient

    # Create client that doesn't re-raise exceptions
    test_client = StarletteTestClient(client.app, raise_server_exceptions=False)
    response = test_client.get("/test-unexpected")
    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INTERNAL_SERVER_ERROR"
    assert payload["message"] == "Internal server error"
    assert payload["details"]["exception_type"] == "ValueError"
    assert isinstance(payload["request_id"], str) and payload["request_id"]
