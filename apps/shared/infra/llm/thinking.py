"""Map user-facing thinking effort to provider-specific chat request parameters."""

from __future__ import annotations

from typing import Any, Literal

from apps.shared.infra.llm.model_profile import ModelProfile
from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import ResolvedModelConfig
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

ThinkingEffort = Literal["none", "low", "medium", "high"]
DEFAULT_THINKING_EFFORT: ThinkingEffort = "none"
VALID_THINKING_EFFORTS = frozenset({"none", "low", "medium", "high"})

# Provider preset metadata.thinking_request_mode (see providers.yaml)
THINKING_MODE_OMIT = "omit"
THINKING_MODE_EXTRA_BODY = "extra_body_thinking"
THINKING_MODE_REASONING_EFFORT = "reasoning_effort"


def normalize_thinking_effort(value: str | None) -> ThinkingEffort:
    if value in VALID_THINKING_EFFORTS:
        return value  # type: ignore[return-value]
    return DEFAULT_THINKING_EFFORT


def _resolve_catalog_profile(resolved: ResolvedModelConfig) -> ModelProfile | None:
    catalog = get_provider_catalog()
    if resolved.catalog_model_key:
        profile = catalog.get_profile(resolved.catalog_model_key)
        if profile is not None:
            return profile
    return catalog.find_llm_profile(resolved.provider_preset_key, resolved.model_id)


def _thinking_request_mode(resolved: ResolvedModelConfig) -> str | None:
    catalog = get_provider_catalog()
    preset_key = resolved.provider_preset_key
    if preset_key:
        preset = catalog.get_preset(preset_key)
        if preset is not None:
            mode = preset.metadata.get("thinking_request_mode")
            if isinstance(mode, str) and mode.strip():
                return mode.strip()
    profile = _resolve_catalog_profile(resolved)
    if profile is not None:
        mode = profile.metadata.get("thinking_request_mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return None


_EFFORT_MAP_OMIT = "omit"


def _normalize_effort_map(raw: dict[Any, Any]) -> dict[str, str]:
    """Normalize YAML map keys (some loaders parse unquoted none as null)."""
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        level = "none" if key is None else str(key)
        if value is None or value == _EFFORT_MAP_OMIT:
            normalized[level] = _EFFORT_MAP_OMIT
        else:
            normalized[level] = str(value)
    return normalized


def _thinking_effort_map(resolved: ResolvedModelConfig) -> dict[str, str] | None:
    """Catalog thinking_effort_map: workbench level -> API value or 'omit'."""
    profile = _resolve_catalog_profile(resolved)
    if profile is not None:
        raw = profile.metadata.get("thinking_effort_map")
        if isinstance(raw, dict) and raw:
            return _normalize_effort_map(raw)
    preset_key = resolved.provider_preset_key
    if preset_key:
        preset = get_provider_catalog().get_preset(preset_key)
        if preset is not None:
            for key in ("thinking_effort_map", "thinking_effort_map_default"):
                raw = preset.metadata.get(key)
                if isinstance(raw, dict) and raw:
                    return _normalize_effort_map(raw)
    return None


def map_reasoning_effort_param(effort: ThinkingEffort, resolved: ResolvedModelConfig) -> str | None:
    """Map workbench effort to provider reasoning_effort; None omits the field."""
    effort_map = _thinking_effort_map(resolved)
    if effort_map is not None:
        if effort not in effort_map:
            return None if effort == "none" else effort
        mapped = effort_map[effort]
        if mapped is None or mapped == _EFFORT_MAP_OMIT:
            return None
        return str(mapped)
    if effort == "none":
        return None
    return effort


def thinking_effort_none_disables(resolved: ResolvedModelConfig) -> bool:
    """True when workbench 'none' maps to API reasoning_effort 'none' (explicit disable)."""
    return map_reasoning_effort_param("none", resolved) == "none"


def model_supports_thinking(resolved: ResolvedModelConfig) -> bool:
    """Whether extended thinking can be requested (catalog model metadata only)."""
    profile = _resolve_catalog_profile(resolved)
    return bool(profile and profile.metadata.get("supports_thinking") is True)


def coerce_thinking_effort(
    effort: str | None,
    resolved: ResolvedModelConfig,
) -> tuple[ThinkingEffort, bool]:
    """Return effective effort and whether the model supports non-none effort."""
    normalized = normalize_thinking_effort(effort)
    supports = model_supports_thinking(resolved)
    if normalized != "none" and not supports:
        logger.info(
            "Thinking effort '%s' ignored for model '%s' (preset=%s); "
            "catalog has no supports_thinking for this model",
            normalized,
            resolved.model_id,
            resolved.provider_preset_key,
        )
        return "none", False
    return normalized, supports


def build_thinking_request_payload(
    effort: ThinkingEffort,
    resolved: ResolvedModelConfig,
) -> dict[str, Any] | None:
    """Provider payload fragment for observability (not necessarily full extra_body)."""
    mode = _thinking_request_mode(resolved)
    if mode == THINKING_MODE_OMIT or mode is None:
        return None
    if mode == THINKING_MODE_EXTRA_BODY:
        if effort == "none":
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled", "effort": effort}}
    if mode == THINKING_MODE_REASONING_EFFORT:
        param = map_reasoning_effort_param(effort, resolved)
        if param is not None:
            return {"reasoning_effort": param}
        effort_map = _thinking_effort_map(resolved)
        if effort_map and effort in effort_map and effort_map[effort] == _EFFORT_MAP_OMIT:
            return {"reasoning_effort": "(omitted — provider default applies)"}
        return None
    return None


def apply_thinking_to_chat_kwargs(
    kwargs: dict[str, Any],
    *,
    resolved: ResolvedModelConfig,
    thinking_effort: ThinkingEffort,
) -> None:
    """Mutate ChatOpenAI kwargs for the given thinking effort."""
    mode = _thinking_request_mode(resolved)
    if mode is None or mode == THINKING_MODE_OMIT:
        return

    if mode == THINKING_MODE_EXTRA_BODY:
        extra = dict(kwargs.get("extra_body") or {})
        if thinking_effort == "none":
            extra["thinking"] = {"type": "disabled"}
        else:
            extra["thinking"] = {"type": "enabled"}
        kwargs["extra_body"] = extra
        return

    if mode == THINKING_MODE_REASONING_EFFORT:
        param = map_reasoning_effort_param(thinking_effort, resolved)
        if param is not None:
            kwargs["reasoning_effort"] = param
