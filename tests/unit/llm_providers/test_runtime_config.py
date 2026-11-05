"""Runtime config seeding from catalog (create / reset / backfill only)."""

from datetime import UTC, datetime

from apps.shared.llm_providers.domain import LLMModelProfileDomain, ModelProfileCategory, ModelProfileSource
from apps.shared.llm_providers.runtime_config import (
    seed_provider_config_from_catalog,
    seed_reasoning_config_from_catalog,
)

_NOW = datetime.now(UTC)


def _llm_profile(**kwargs: object) -> LLMModelProfileDomain:
    base = dict(
        id=1,
        tenant_id=1,
        provider_id=1,
        name="DBX GLM",
        category=ModelProfileCategory.LLM,
        model_id="system.ai.glm-5-3",
        params=None,
        reasoning_config=None,
        catalog_model_key="databricks-ai-gateway/system.ai.glm-5-3",
        source=ModelProfileSource.PRESET,
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(kwargs)
    return LLMModelProfileDomain(**base)  # type: ignore[arg-type]


def test_seed_provider_config_from_databricks_preset():
    cfg = seed_provider_config_from_catalog("databricks-ai-gateway")
    assert cfg == {"thinking_request_mode": "reasoning_effort"}


def test_seed_reasoning_config_from_catalog_model():
    config = seed_reasoning_config_from_catalog(
        _llm_profile(),
        provider_preset_key="databricks-ai-gateway",
    )
    assert config is not None
    assert config["supports_thinking"] is True
    assert [o["value"] for o in config["thinking_effort_options"]] == ["low", "high", "max"]


def test_seed_reasoning_config_reads_catalog_default_thinking_effort(monkeypatch):
    from apps.shared.infra.llm.model_profile import ModelProfile
    from apps.shared.llm_providers import runtime_config

    fake_profile = ModelProfile(
        key="test/gateway-model",
        name="Gateway Model",
        provider="databricks",
        model_id="system.ai.test-model",
        metadata={
            "supports_thinking": True,
            "thinking_effort_options": ["low", "high", "max"],
            "default_thinking_effort": "max",
        },
    )

    def fake_catalog_model_profile(**_kwargs):
        return fake_profile

    monkeypatch.setattr(runtime_config, "_catalog_model_profile", fake_catalog_model_profile)

    config = seed_reasoning_config_from_catalog(
        _llm_profile(catalog_model_key="test/gateway-model", model_id="system.ai.test-model"),
        provider_preset_key="databricks-ai-gateway",
    )
    assert config is not None
    assert config.get("default_thinking_effort") == "max"
