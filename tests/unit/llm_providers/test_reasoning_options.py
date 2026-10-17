"""thinking_effort_options normalization."""

from apps.shared.llm_providers.reasoning_options import (
    default_thinking_effort_value,
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
