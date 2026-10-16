"""Catalog YAML thinking_effort_map for Databricks gateway models."""

from apps.shared.infra.llm.thinking import (
    _normalize_effort_map,
    build_thinking_request_payload,
    map_reasoning_effort_param,
    thinking_effort_none_disables,
)
from apps.shared.llm_providers.domain import ModelProfileCategory, ResolvedModelConfig


def _resolved(model_id: str) -> ResolvedModelConfig:
    preset = "databricks-ai-gateway"
    return ResolvedModelConfig(
        profile_id=1,
        profile_name="Test",
        category=ModelProfileCategory.LLM,
        model_id=model_id,
        params={},
        provider_id=1,
        provider_display_name="DBX",
        provider_type="openai-compatible",
        provider_preset_key=preset,
        api_base="https://example.com/v1",
        api_key="key",
        catalog_model_key=f"{preset}/{model_id}",
    )


def test_normalize_effort_map_null_yaml_none_key():
    assert _normalize_effort_map({None: None}) == {"none": "omit"}
    assert _normalize_effort_map({"none": "none"}) == {"none": "none"}


def test_deepseek_v41_none_sends_disable():
    assert map_reasoning_effort_param("none", _resolved("system.ai.deepseek-v4-1-flash")) == "none"


def test_deepseek_v41_medium_maps_to_high():
    assert map_reasoning_effort_param("medium", _resolved("system.ai.deepseek-v4-1-flash")) == "high"


def test_glm_53_none_maps_to_minimum_low():
    resolved = _resolved("system.ai.glm-5-3-flash")
    assert map_reasoning_effort_param("none", resolved) == "low"
    assert thinking_effort_none_disables(resolved) is False
    assert build_thinking_request_payload("none", resolved) == {"reasoning_effort": "low"}


def test_deepseek_v41_none_disables():
    resolved = _resolved("system.ai.deepseek-v4-1-flash")
    assert thinking_effort_none_disables(resolved) is True


def test_deepseek_v4_flash_high_maps_to_max():
    assert map_reasoning_effort_param("high", _resolved("system.ai.deepseek-v4-flash-0731")) == "max"


def test_deepseek_v4_flash_0731_none_maps_to_low():
    resolved = _resolved("system.ai.deepseek-v4-flash-0731")
    assert map_reasoning_effort_param("none", resolved) == "low"
    assert thinking_effort_none_disables(resolved) is False


def test_deepseek_v41_high_maps_to_max():
    assert map_reasoning_effort_param("high", _resolved("system.ai.deepseek-v4-1-flash")) == "max"
    assert build_thinking_request_payload("high", _resolved("system.ai.deepseek-v4-1-flash")) == {
        "reasoning_effort": "max"
    }


def test_gemini_31_pro_high_for_reasoning_content_verification():
    resolved = _resolved("system.ai.gemini-3-1-pro")
    assert map_reasoning_effort_param("high", resolved) == "high"
    assert build_thinking_request_payload("medium", resolved) == {"reasoning_effort": "medium"}
