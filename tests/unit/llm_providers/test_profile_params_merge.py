"""Profile params stored in DB are passed through at resolve (no catalog merge at runtime)."""

from datetime import UTC, datetime

from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import LLMModelProfileDomain, ModelProfileCategory, ModelProfileSource

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
        reasoning_config=None,
        catalog_model_key=catalog_model_key,
        source=ModelProfileSource.PRESET,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_gpt_55_catalog_declares_temperature_one():
    profile = get_provider_catalog().get_profile(_GPT55_KEY)
    assert profile is not None
    assert profile.get_default_temperature() == 1


def test_stored_params_are_used_as_is():
    profile = _profile(params={"temperature": 0.5, "max_tokens": 8000})
    assert profile.params == {"temperature": 0.5, "max_tokens": 8000}
