"""Thinking effort selection from profile DB snapshots."""

from datetime import UTC, datetime

from apps.shared.infra.llm.thinking import (
    apply_thinking_to_chat_kwargs,
    coerce_thinking_effort_value,
    model_supports_thinking,
)
from apps.shared.llm_providers.domain import ModelProfileCategory, ResolvedModelConfig


def _resolved(*, reasoning_config: dict | None, provider_config: dict | None = None) -> ResolvedModelConfig:
    return ResolvedModelConfig(
        profile_id=1,
        profile_name="Test",
        category=ModelProfileCategory.LLM,
        model_id="test-model",
        params=None,
        provider_id=1,
        provider_display_name="Provider",
        provider_type="openai-compatible",
        provider_preset_key="bailian",
        api_base="https://example.com/v1",
        api_key="key",
        reasoning_config=reasoning_config,
        provider_config=provider_config or {"thinking_request_mode": "extra_body_thinking"},
    )


def test_coerce_uses_first_option_as_default():
    resolved = _resolved(
        reasoning_config={
            "supports_thinking": True,
            "thinking_effort_options": [{"name": "Off", "value": "none"}, "low", "high"],
        }
    )
    value, supports = coerce_thinking_effort_value(None, resolved)
    assert supports is True
    assert value == "none"


def test_coerce_rejects_unknown_selection():
    resolved = _resolved(
        reasoning_config={
            "supports_thinking": True,
            "thinking_effort_options": ["low", "max"],
        }
    )
    value, _ = coerce_thinking_effort_value("medium", resolved)
    assert value == "low"


def test_model_supports_thinking_requires_options():
    assert model_supports_thinking(_resolved(reasoning_config={"supports_thinking": True})) is False
    assert (
        model_supports_thinking(
            _resolved(
                reasoning_config={
                    "supports_thinking": True,
                    "thinking_effort_options": ["low"],
                }
            )
        )
        is True
    )


def test_extra_body_none_disables():
    resolved = _resolved(
        reasoning_config={
            "supports_thinking": True,
            "thinking_effort_options": [{"name": "Off", "value": "none"}, "low"],
        }
    )
    kwargs: dict = {}
    apply_thinking_to_chat_kwargs(kwargs, resolved=resolved, thinking_effort="none")
    assert kwargs["extra_body"]["thinking"]["type"] == "disabled"


def test_extra_body_low_enables():
    resolved = _resolved(
        reasoning_config={
            "supports_thinking": True,
            "thinking_effort_options": [{"name": "Off", "value": "none"}, "low"],
        }
    )
    kwargs: dict = {}
    apply_thinking_to_chat_kwargs(kwargs, resolved=resolved, thinking_effort="low")
    assert kwargs["extra_body"]["thinking"]["type"] == "enabled"
