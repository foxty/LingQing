"""Thinking effort mapping for LLM chat requests."""

from apps.shared.infra.llm.thinking import (
    apply_thinking_to_chat_kwargs,
    coerce_thinking_effort,
    normalize_thinking_effort,
)
from apps.shared.llm_providers.domain import ModelProfileCategory, ResolvedModelConfig


def _resolved(*, preset: str | None = "bailian", model_id: str = "qwen3.5-plus") -> ResolvedModelConfig:
    return ResolvedModelConfig(
        profile_id=1,
        profile_name="Test",
        category=ModelProfileCategory.LLM,
        model_id=model_id,
        params={},
        provider_id=1,
        provider_display_name="Bailian",
        provider_type="openai-compatible",
        provider_preset_key=preset,
        api_base="https://example.com/v1",
        api_key="key",
        catalog_model_key=f"{preset}/{model_id}" if preset else None,
    )


def test_normalize_invalid_defaults_to_none():
    assert normalize_thinking_effort(None) == "none"
    assert normalize_thinking_effort("invalid") == "none"


def test_coerce_unsupported_model_to_none():
    # Bailian preset but model not marked supports_thinking in catalog
    resolved = _resolved(preset="bailian", model_id="unknown-model")
    effort, supports = coerce_thinking_effort("high", resolved)
    assert effort == "none"
    assert supports is False


def test_coerce_supported_qwen_model():
    effort, supports = coerce_thinking_effort("medium", _resolved())
    assert effort == "medium"
    assert supports is True


def test_apply_thinking_disabled_by_default():
    kwargs: dict = {}
    apply_thinking_to_chat_kwargs(kwargs, resolved=_resolved(), thinking_effort="none")
    assert kwargs["extra_body"]["thinking"]["type"] == "disabled"


def test_apply_thinking_enabled_for_bailian():
    kwargs: dict = {}
    apply_thinking_to_chat_kwargs(kwargs, resolved=_resolved(), thinking_effort="low")
    assert kwargs["extra_body"]["thinking"]["type"] == "enabled"
