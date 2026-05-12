"""Test exception handlers."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateResourceError,
    InternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)


@pytest.fixture
def app():
    """Create a test FastAPI app with exception handlers."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/test-not-found")
    async def test_not_found():
        raise ResourceNotFoundError("Resource not found")

    @app.get("/test-duplicate")
    async def test_duplicate():
        raise DuplicateResourceError("Resource already exists")

    @app.get("/test-validation")
    async def test_validation():
        raise ValidationError("Validation failed")

    @app.get("/test-authentication")
    async def test_authentication():
        raise AuthenticationError("Authentication failed")

    @app.get("/test-authorization")
    async def test_authorization():
        raise AuthorizationError("Authorization failed")

    @app.get("/test-internal")
    async def test_internal():
        raise InternalServiceError("Internal error")

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


def test_resource_not_found_handler(client):
    """Test ResourceNotFoundError handler returns 404."""
    response = client.get("/test-not-found")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "RESOURCE_NOT_FOUND"
    assert payload["message"] == "Resource not found"
    assert payload["details"] == {}
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_duplicate_resource_handler(client):
    """Test DuplicateResourceError handler returns 409."""
    response = client.get("/test-duplicate")
    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "RESOURCE_CONFLICT"
    assert payload["message"] == "Resource already exists"
    assert payload["details"] == {}
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_validation_error_handler(client):
    """Test ValidationError handler returns 400."""
    response = client.get("/test-validation")
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["message"] == "Validation failed"
    assert payload["details"] == {}
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_authentication_error_handler(client):
    """Test AuthenticationError handler returns 401."""
    response = client.get("/test-authentication")
    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "AUTHENTICATION_FAILED"
    assert payload["message"] == "Authentication failed"
    assert payload["details"] == {}
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_authorization_error_handler(client):
    """Test AuthorizationError handler returns 403."""
    response = client.get("/test-authorization")
    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "AUTHORIZATION_FAILED"
    assert payload["message"] == "Authorization failed"
    assert payload["details"] == {}
    assert isinstance(payload["request_id"], str) and payload["request_id"]


def test_internal_service_error_handler(client):
    """Test InternalServiceError handler returns 500."""
    response = client.get("/test-internal")
    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INTERNAL_SERVICE_ERROR"
    assert payload["message"] == "Internal error"
    assert payload["details"] == {}
    assert isinstance(payload["request_id"], str) and payload["request_id"]
