"""Tests for agent catalog adapters (DB ↔ API DTO resolution)."""

from apps.tenant_app_service.agent_catalog.adapters import (
    capability_config_dto_for_response,
    effective_max_loop_iterations,
    normalize_max_loop_for_storage,
)
from apps.tenant_app_service.agent_catalog.domain import AgentCapabilityProfile


def test_normalize_max_loop_for_storage_clears_platform_default(monkeypatch):
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.adapters.effective_max_loop_iterations",
        lambda profile=None: 50,
    )
    assert normalize_max_loop_for_storage(50) is None
    assert normalize_max_loop_for_storage(80) == 80
    assert normalize_max_loop_for_storage(None) is None


def test_capability_config_dto_for_response_includes_effective_max_loop(monkeypatch):
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.adapters.effective_max_loop_iterations",
        lambda profile: 50,
    )
    dto = capability_config_dto_for_response(
        AgentCapabilityProfile(skills=["data_analyst"]),
        default_tools=["search_documents"],
    )
    assert dto.max_loop_iterations == 50
    assert dto.default_tools == ["search_documents"]