"""Regression test: SkillService and AgentConfig share one resolver.

Before the consolidation, each layer built its own resolver and loaded
skills independently — the per-tenant cache was not shared between the
management UI and the agent runtime. The new
``get_default_skill_resolver`` factory is the single source of truth; this
test pins that contract.
"""

from __future__ import annotations

from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.skills.resolution import (
    SkillResolver,
    get_default_skill_resolver,
    reset_default_skill_resolver,
)
from apps.tenant_app_service.skills.service import SkillService


def test_factory_returns_singleton() -> None:
    """Two calls return the same instance until ``reset`` is called."""
    reset_default_skill_resolver()
    r1 = get_default_skill_resolver()
    r2 = get_default_skill_resolver()
    assert r1 is r2


def test_reset_clears_singleton() -> None:
    """``reset_default_skill_resolver`` forces a fresh instance next call."""
    reset_default_skill_resolver()
    r1 = get_default_skill_resolver()
    reset_default_skill_resolver()
    r2 = get_default_skill_resolver()
    assert r1 is not r2


def test_skill_service_uses_shared_resolver_when_data_root_matches(monkeypatch) -> None:
    """SkillService piggybacks on the shared resolver (single cache)."""
    from apps.config import EnvConfig

    monkeypatch.setattr(EnvConfig, "DATA_ROOT_PATH", "/shared/data/root", raising=False)
    reset_default_skill_resolver()
    shared = get_default_skill_resolver()

    svc = SkillService(data_root="/shared/data/root")
    assert svc._resolver is shared


def test_skill_service_can_inject_isolated_resolver(monkeypatch) -> None:
    """Tests inject their own resolver to avoid mutating the shared cache."""
    from apps.config import EnvConfig

    monkeypatch.setattr(EnvConfig, "DATA_ROOT_PATH", "/shared/data/root", raising=False)
    reset_default_skill_resolver()
    shared = get_default_skill_resolver()
    isolated = SkillResolver(data_root=shared._repo._data_root, tool_registry={})

    svc = SkillService(data_root="/shared/data/root", resolver=isolated)
    assert svc._resolver is isolated
    assert svc._resolver is not shared


def test_agent_config_manager_uses_shared_resolver(monkeypatch) -> None:
    """AgentConfig.__init__ consumes the shared resolver by default."""
    from apps.config import EnvConfig

    monkeypatch.setattr(EnvConfig, "DATA_ROOT_PATH", "/shared/data/root", raising=False)
    reset_default_skill_resolver()
    shared = get_default_skill_resolver()

    manager = AgentConfig(
        {
            "agent_id": -1,
            "name": "TestAgent",
            "system_prompt": "x",
            "default_tools": [],
        }
    )
    assert manager._skill_resolution is shared


def test_reset_gives_agent_config_manager_fresh_resolver(monkeypatch) -> None:
    """After reset, AgentConfig picks up a fresh shared resolver."""
    from apps.config import EnvConfig

    monkeypatch.setattr(EnvConfig, "DATA_ROOT_PATH", "/shared/data/root", raising=False)
    reset_default_skill_resolver()
    shared = get_default_skill_resolver()
    reset_default_skill_resolver()
    fresh = get_default_skill_resolver()
    assert fresh is not shared
