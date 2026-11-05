"""thinking_effort_options normalization."""

from apps.shared.llm_providers.reasoning_options import (
    default_thinking_effort_from_reasoning_config,
    default_thinking_effort_value,
    normalize_reasoning_config,
    normalize_thinking_effort_options,
    thinking_effort_options_from_reasoning_config,
)


def test_normalize_string_options():
    opts = normalize_thinking_effort_options(["low", "high", "max"])
    assert opts == [
        {"name": "low", "value": "low"},
        {"name": "high", "value": "high"},
        {"name": "max", "value": "max"},
    ]
    assert default_thinking_effort_value(opts) == "low"


def test_normalize_named_option():
    opts = normalize_thinking_effort_options([{"name": "Off", "value": "none"}, "low"])
    assert opts[0] == {"name": "Off", "value": "none"}
    assert opts[1]["value"] == "low"


def test_reasoning_config_reads_options_only():
    opts = thinking_effort_options_from_reasoning_config(
        {"supports_thinking": True, "thinking_effort_options": ["none", "max"]}
    )
    assert [o["value"] for o in opts] == ["none", "max"]

    assert thinking_effort_options_from_reasoning_config({"supports_thinking": True}) == []


def test_default_from_explicit_profile_field():
    reasoning = {
        "supports_thinking": True,
        "thinking_effort_options": ["none", "low", "max"],
        "default_thinking_effort": "max",
    }
    assert default_thinking_effort_from_reasoning_config(reasoning) == "max"


def test_default_falls_back_to_first_option_when_explicit_missing():
    reasoning = {
        "supports_thinking": True,
        "thinking_effort_options": ["none", "low", "max"],
    }
    assert default_thinking_effort_from_reasoning_config(reasoning) == "none"


def test_default_ignores_invalid_explicit():
    reasoning = {
        "supports_thinking": True,
        "thinking_effort_options": ["low", "max"],
        "default_thinking_effort": "medium",
    }
    assert default_thinking_effort_from_reasoning_config(reasoning) == "low"


def test_normalize_reasoning_config_strips_invalid_default():
    normalized = normalize_reasoning_config(
        {
            "supports_thinking": True,
            "thinking_effort_options": ["low"],
            "default_thinking_effort": "high",
        }
    )
    assert normalized is not None
    assert "default_thinking_effort" not in normalized


def test_default_thinking_effort_value_prefers_explicit_when_valid():
    opts = [
        {"name": "Off", "value": "none"},
        {"name": "Max", "value": "max"},
    ]
    assert default_thinking_effort_value(opts, explicit_default="max") == "max"
    assert default_thinking_effort_value(opts, explicit_default="missing") == "none"


def test_normalize_reasoning_config_keeps_valid_default():
    normalized = normalize_reasoning_config(
        {
            "supports_thinking": True,
            "thinking_effort_options": ["none", "low", "max"],
            "default_thinking_effort": "max",
        }
    )
    assert normalized is not None
    assert normalized["default_thinking_effort"] == "max"
    assert [o["value"] for o in normalized["thinking_effort_options"]] == ["none", "low", "max"]


def test_normalize_reasoning_config_clears_default_when_thinking_disabled():
    normalized = normalize_reasoning_config(
        {
            "supports_thinking": False,
            "thinking_effort_options": ["low"],
            "default_thinking_effort": "low",
        }
    )
    assert normalized == {"supports_thinking": False, "thinking_effort_options": []}
