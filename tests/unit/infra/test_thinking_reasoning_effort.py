"""reasoning_effort wire mode using profile thinking_effort_options."""

from datetime import UTC, datetime

from apps.shared.infra.llm.thinking import (
    apply_thinking_to_chat_kwargs,
    build_thinking_request_payload,
    selection_disables_reasoning_on_wire,
)
from apps.shared.llm_providers.domain import LLMModelProfileDomain, ModelProfileCategory, ModelProfileSource, ResolvedModelConfig
from apps.shared.llm_providers.runtime_config import seed_reasoning_config_from_catalog

_NOW = datetime.now(UTC)
_CATALOG_PRESET = "databricks-ai-gateway"


def _resolved(model_id: str, *, reasoning_config: dict | None = None) -> ResolvedModelConfig:
    draft = LLMModelProfileDomain(
        id=1,
        tenant_id=1,
        provider_id=1,
        name="DBX",
        category=ModelProfileCategory.LLM,
        model_id=model_id,
        params=None,
        reasoning_config=reasoning_config,
        catalog_model_key=f"{_CATALOG_PRESET}/{model_id}",
        source=ModelProfileSource.PRESET,
        created_at=_NOW,
        updated_at=_NOW,
    )
    if reasoning_config is None:
        reasoning_config = seed_reasoning_config_from_catalog(draft, provider_preset_key=_CATALOG_PRESET)
    return ResolvedModelConfig(
        profile_id=1,
        profile_name="DBX",
        category=ModelProfileCategory.LLM,
        model_id=model_id,
        params=None,
        provider_id=1,
        provider_display_name="DBX",
        provider_type="openai-compatible",
        provider_preset_key=_CATALOG_PRESET,
        api_base="https://example.com/v1",
        api_key="key",
        reasoning_config=reasoning_config,
        provider_config={"thinking_request_mode": "reasoning_effort"},
    )


def test_seed_glm_options_from_catalog():
    resolved = _resolved("system.ai.glm-5-3")
    options = resolved.reasoning_config.get("thinking_effort_options") if resolved.reasoning_config else []
    assert [o["value"] for o in options] == ["low", "high", "max"]


def test_apply_reasoning_effort_max():
    resolved = _resolved("system.ai.glm-5-3")
    kwargs: dict = {}
    apply_thinking_to_chat_kwargs(kwargs, resolved=resolved, thinking_effort="max")
    assert kwargs["reasoning_effort"] == "max"


def test_explicit_none_disables():
    resolved = _resolved("system.ai.deepseek-v4-1-flash")
    assert selection_disables_reasoning_on_wire("none", resolved) is True
    kwargs: dict = {}
    apply_thinking_to_chat_kwargs(kwargs, resolved=resolved, thinking_effort="none")
    assert kwargs["reasoning_effort"] == "none"


def test_build_payload_reasoning_effort():
    resolved = _resolved("system.ai.glm-5-3")
    assert build_thinking_request_payload("low", resolved) == {"reasoning_effort": "low"}
