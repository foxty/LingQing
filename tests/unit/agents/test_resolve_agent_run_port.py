"""Tests for ``resolve_agent_run_port``."""

from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.agents.ports.resolve_agent_run_port import resolve_agent_run_port


def test_resolve_agent_run_port():
    port = object()
    config = RunnableConfig(configurable={"agent_run_port": port})
    assert resolve_agent_run_port(config) is port


def test_resolve_missing_raises():
    with pytest.raises(ValidationError, match="agent_run_port"):
        resolve_agent_run_port(RunnableConfig(configurable={"run_id": str(uuid4())}))
