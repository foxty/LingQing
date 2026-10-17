"""Seed tenant LLM runtime config from platform catalog (create / reset / backfill only)."""

from __future__ import annotations

from typing import Any

from apps.shared.infra.llm.model_profile import ModelProfile
from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import LLMModelProfileDomain, ModelProfileCategory
from apps.shared.llm_providers.reasoning_options import normalize_thinking_effort_options

VALID_THINKING_MODES = frozenset({"omit", "extra_body_thinking", "reasoning_effort"})


def _catalog_model_profile(
    *,
    catalog_model_key: str | None,
    provider_preset_key: str | None,
    model_id: str,
    category: ModelProfileCategory,
) -> ModelProfile | None:
    catalog = get_provider_catalog()
    if catalog_model_key:
        profile = catalog.get_profile(catalog_model_key)
        if profile is not None:
            return profile
    if category == ModelProfileCategory.LLM and provider_preset_key:
        return catalog.find_llm_profile(provider_preset_key, model_id)
    return None


def _provider_thinking_request_mode(provider_preset_key: str | None) -> str | None:
    if not provider_preset_key:
        return None
    preset = get_provider_catalog().get_preset(provider_preset_key)
    if preset is None:
        return None
    mode = (preset.metadata or {}).get("thinking_request_mode")
    return mode.strip() if isinstance(mode, str) and mode.strip() else None


def _default_thinking_effort_options(*, supports_thinking: bool, thinking_request_mode: str | None) -> list[Any] | None:
    if not supports_thinking:
        return None
    if thinking_request_mode == "extra_body_thinking":
        return [{"name": "Off", "value": "none"}, "low", "medium", "high"]
    if thinking_request_mode == "reasoning_effort":
        return ["low", "medium", "high"]
    return ["low", "medium", "high"]


def seed_params_from_catalog(
    profile: LLMModelProfileDomain,
    *,
    provider_preset_key: str | None,
) -> dict[str, Any] | None:
    """Full sampling-params snapshot from catalog (global + model defaults)."""
    catalog_profile = _catalog_model_profile(
        catalog_model_key=profile.catalog_model_key,
        provider_preset_key=provider_preset_key,
        model_id=profile.model_id,
        category=profile.category,
    )
    if catalog_profile and catalog_profile.default_params:
        return dict(catalog_profile.default_params)
    if profile.category == ModelProfileCategory.LLM:
        preset = get_provider_catalog().get_preset(provider_preset_key) if provider_preset_key else None
        if preset and preset.default_params:
            return dict(preset.default_params)
    return None


def seed_reasoning_config_from_catalog(
    profile: LLMModelProfileDomain,
    *,
    provider_preset_key: str | None,
) -> dict[str, Any] | None:
    """Model-level reasoning capabilities snapshot for LLM profiles."""
    if profile.category != ModelProfileCategory.LLM:
        return None

    catalog_profile = _catalog_model_profile(
        catalog_model_key=profile.catalog_model_key,
        provider_preset_key=provider_preset_key,
        model_id=profile.model_id,
        category=profile.category,
    )
    if catalog_profile is None:
        return {"supports_thinking": False}

    metadata = catalog_profile.metadata or {}
    supports_thinking = metadata.get("supports_thinking") is True
    config: dict[str, Any] = {
        "supports_thinking": supports_thinking,
    }
    options = normalize_thinking_effort_options(metadata.get("thinking_effort_options"))
    if not options and supports_thinking:
        mode = _provider_thinking_request_mode(provider_preset_key)
        fallback_raw = _default_thinking_effort_options(
            supports_thinking=supports_thinking,
            thinking_request_mode=mode,
        )
        options = normalize_thinking_effort_options(fallback_raw)
    if options:
        config["thinking_effort_options"] = options
    if metadata.get("exposes_thinking_content") is True:
        config["exposes_thinking_content"] = True
    return config


def seed_provider_config_from_catalog(preset_key: str | None) -> dict[str, Any] | None:
    """Snapshot preset-level metadata into llm_providers.config (extensible JSON)."""
    if not preset_key:
        return None
    preset = get_provider_catalog().get_preset(preset_key)
    if preset is None:
        return None
    raw = dict(preset.metadata or {})
    if not raw:
        return None
    mode = raw.get("thinking_request_mode")
    if isinstance(mode, str):
        stripped = mode.strip()
        if stripped in VALID_THINKING_MODES:
            raw["thinking_request_mode"] = stripped
        else:
            raw.pop("thinking_request_mode", None)
    return raw or None
