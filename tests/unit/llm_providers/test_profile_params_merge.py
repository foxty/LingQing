"""Resolve-time merge of catalog default_params and tenant profile params."""

from datetime import UTC, datetime

from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import LLMModelProfileDomain, ModelProfileCategory, ModelProfileSource
from apps.shared.llm_providers.service import _effective_profile_params

_GPT55_KEY = "databricks-ai-gateway/system.ai.gpt-5-5"
_NOW = datetime.now(UTC)


def _profile(
    *,
    params: dict | None,
    catalog_model_key: str | None = _GPT55_KEY,
) -> LLMModelProfileDomain:
    return LLMModelProfileDomain(
        id=1,
        tenant_id=1,
        provider_id=1,
        name="GPT 5.5",
        category=ModelProfileCategory.LLM,
        model_id="system.ai.gpt-5-5",
        params=params,
        catalog_model_key=catalog_model_key,
        source=ModelProfileSource.PRESET,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_gpt_55_catalog_declares_temperature_one():
    profile = get_provider_catalog().get_profile(_GPT55_KEY)
    assert profile is not None
    assert profile.get_default_temperature() == 1


def test_effective_params_uses_catalog_when_profile_params_empty():
    merged = _effective_profile_params(
        _profile(params=None),
        provider_preset_key="databricks-ai-gateway",
    )
    assert merged is not None
    assert merged["temperature"] == 1


def test_effective_params_tenant_overrides_catalog():
    merged = _effective_profile_params(
        _profile(params={"temperature": 0.5}),
        provider_preset_key="databricks-ai-gateway",
    )
    assert merged["temperature"] == 0.5


def test_effective_params_without_catalog_key_returns_stored_params_only():
    merged = _effective_profile_params(
        _profile(params={"temperature": 0.3}, catalog_model_key=None),
        provider_preset_key=None,
    )
    assert merged == {"temperature": 0.3}
