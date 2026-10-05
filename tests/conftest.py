"""Pytest configuration for testing strategy.

This file configures pytest to properly handle:
- Unit tests (fast, no external dependencies)
- Integration tests (slower, require running server)
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict

import pytest

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Set up test environment variables BEFORE any module imports
# This is critical for apps.config which is imported by many modules
_temp_dir = tempfile.mkdtemp()
os.environ["DATA_ROOT_PATH"] = _temp_dir
os.environ["TENANT_APP_DB_USER"] = "test_user"
os.environ["TENANT_APP_DB_PASSWORD"] = "test_password"
os.environ["TENANT_APP_DB_NAME"] = "test_db"
os.environ["TENANT_APP_DB_HOST"] = "localhost"
os.environ["SECRET_KEY"] = "test-secret-key"
# Isolate from developer .env.local (may set CHROMA_MODE=http without CHROMA_URL).
os.environ["CHROMA_MODE"] = "embedded"
os.environ.pop("CHROMA_URL", None)


def _isolate_parser_env() -> None:
    os.environ["DOCUMENT_PARSER"] = "default"
    os.environ.pop("DOCLING_SERVICE_URL", None)
    os.environ.pop("DOCLING_API_KEY", None)
    os.environ.pop("DOCLING_DO_OCR", None)
    os.environ.pop("MINERU_SERVICE_URL", None)


_isolate_parser_env()

def pytest_configure(config):
    """Configure pytest markers and options."""
    _isolate_parser_env()
    config.addinivalue_line("markers", "unit: marks tests as unit tests (fast, no external dependencies)")
    config.addinivalue_line("markers", "integration: marks tests as integration tests (require running server)")
    config.addinivalue_line("markers", "slow: marks tests as slow running")
    config.addinivalue_line(
        "markers",
        "docling: marks tests that require a live Docling service (local dev only; excluded from CI)",
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Auto-mark unit tests
        if "tests/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Auto-mark integration tests
        elif "tests/integration/" in str(item.fspath) or "tests/docling_integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)

        # Mark existing API and utils tests as unit tests
        elif any(path in str(item.fspath) for path in ["tests/api/", "tests/utils/"]):
            item.add_marker(pytest.mark.unit)


# Test discovery patterns
collect_ignore = [
    "tests/conftest.py",
]


@pytest.fixture(scope="session", autouse=True)
def test_environment_setup():
    """Setup test environment based on test type."""
    global _temp_dir

    yield

    # Cleanup temp directory after all tests
    shutil.rmtree(_temp_dir, ignore_errors=True)


# === Shared fixtures for agent tests ===


@pytest.fixture
def agent_stub_config_factory() -> Callable[[int, str, str, str], Dict[str, Any]]:
    """Factory to create a minimal agent YAML-like config dict for tests.

    Returns a function that builds a stub config with a `default` role and no tools.
    """

    def _factory(
        agent_id: int = 1,
        agent_name: str = "Test Agent",
        system_prompt: str = "You are a helpful assistant.",
        model_profile_id: int | None = None,
    ) -> Dict[str, Any]:
        config: Dict[str, Any] = {
            "agent_id": agent_id,
            "name": agent_name,
            "system_prompt": system_prompt,
            "roles": {
                "default": {
                    "system_prompt": system_prompt,
                    "tools": [],
                }
            },
        }
        if model_profile_id is not None:
            config["model_profile_id"] = model_profile_id
        return config

    return _factory


@pytest.fixture
def patch_agent_config_manager() -> Callable[[Dict[str, Any]], None]:
    """No-op kept for older tests that still request this fixture.

    Prefer ``AgentBase(stub)`` / ``AgentConfig(stub)``.
    """

    def _apply(_stub_config: Dict[str, Any]) -> None:
        return None

    return _apply


# === Global agent fixtures ===


@pytest.fixture
def runtime_context():
    """Create test runtime context."""
    from apps.tenant_app_service.agents.domain import (
        AgentRuntimeContext,
        AgentTenantContext,
        AgentUserContext,
    )

    return AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=1,
            tenant_name="test_tenant",
            config={},
        ),
        user=AgentUserContext(
            user_id=123,
            username="testuser",
            role="admin",
            tenant_id=1,
            tenant_name="test_tenant",
        ),
        agent_id=456,
        agent_name="test_agent",
        thread_id="thread_test_123",
        session_id="session_test_456",
    )


@pytest.fixture
def runnable_config(runtime_context):
    """Create test RunnableConfig with runtime context."""
    from langchain_core.runnables import RunnableConfig

    return RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
        }
    )


@pytest.fixture(autouse=True)
def cleanup_storage():
    """Clean up storage before each test."""
    from apps.tenant_app_service.agents.metrics.agent_metrics_v3_storage import get_storage

    storage = get_storage("memory")
    # Clear any existing data
    if hasattr(storage, "_events"):
        storage._events.clear()
    if hasattr(storage, "_session_to_thread"):
        storage._session_to_thread.clear()
    yield
    # Clean up after test
    if hasattr(storage, "_events"):
        storage._events.clear()
    if hasattr(storage, "_session_to_thread"):
        storage._session_to_thread.clear()
