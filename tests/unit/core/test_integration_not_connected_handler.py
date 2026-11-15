"""HTTP mapping for IntegrationNotConnectedError."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.core.exceptions import IntegrationNotConnectedError


def test_integration_not_connected_returns_422():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def probe():
        raise IntegrationNotConnectedError("Connect your account", {"resource_id": 1})

    client = TestClient(app)
    response = client.get("/probe")
    assert response.status_code == 422
    body = response.json()
    assert body.get("code") == "INTEGRATION_NOT_CONNECTED" or body.get("detail", {}).get("code")
