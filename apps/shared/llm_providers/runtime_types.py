"""Typed shapes for LLM registry runtime JSON (DB + resolve boundary)."""

from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

ThinkingRequestMode = Literal["omit", "extra_body_thinking", "reasoning_effort"]


class ProviderRuntimeConfig(TypedDict, total=False):
    """llm_providers.config — preset/runtime provider behavior (extensible JSON)."""

    thinking_request_mode: ThinkingRequestMode


class ModelParams(TypedDict, total=False):
    """llm_model_profiles.params — sampling / output caps."""

    temperature: float
    max_tokens: int
    top_p: float


class ThinkingEffortOption(TypedDict):
    name: str
    value: str


class ModelReasoningConfig(TypedDict, total=False):
    """llm_model_profiles.reasoning_config — workbench reasoning capabilities."""

    supports_thinking: bool
    thinking_effort_options: list[ThinkingEffortOption]
    exposes_thinking_content: bool
