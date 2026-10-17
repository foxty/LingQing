"""Apply profile thinking_effort_options to provider chat request parameters."""

from __future__ import annotations

from typing import Any

from apps.shared.llm_providers.domain import ResolvedModelConfig
from apps.shared.llm_providers.reasoning_options import (
    ThinkingEffortOption,
    default_thinking_effort_value,
    thinking_effort_options_from_reasoning_config,
)
from apps.shared.llm_providers.runtime_types import ThinkingRequestMode
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

# Provider llm_providers.config.thinking_request_mode (see providers.yaml)
THINKING_REQUEST_MODE_OMIT: ThinkingRequestMode = "omit"
THINKING_REQUEST_MODE_EXTRA_BODY: ThinkingRequestMode = "extra_body_thinking"
THINKING_REQUEST_MODE_REASONING_EFFORT: ThinkingRequestMode = "reasoning_effort"

_WIRE_NONE = "none"


def list_thinking_effort_options(resolved: ResolvedModelConfig) -> list[ThinkingEffortOption]:
    """Options snapshot from profile reasoning_config (DB)."""
    return thinking_effort_options_from_reasoning_config(resolved.reasoning_config)


def model_supports_thinking(resolved: ResolvedModelConfig) -> bool:
    reasoning = resolved.reasoning_config or {}
    if reasoning.get("supports_thinking") is not True:
        return False
    return bool(list_thinking_effort_options(resolved))


def coerce_thinking_effort_value(
    requested: str | None,
    resolved: ResolvedModelConfig,
) -> tuple[str, bool]:
    """Return effective option value and whether thinking controls apply."""
    options = list_thinking_effort_options(resolved)
    if not options:
        return "", False

    default = default_thinking_effort_value(options)
    allowed = {opt["value"] for opt in options}
    if requested is None or not str(requested).strip():
        return default, True

    value = str(requested).strip()
    if value in allowed:
        return value, True

    logger.info(
        "Thinking effort '%s' not in profile options for model '%s' (profile=%s); using '%s'",
        value,
        resolved.model_id,
        resolved.profile_name,
        default,
    )
    return default, True


def selection_disables_reasoning_on_wire(selection: str, resolved: ResolvedModelConfig) -> bool:
    """True when the selected option value turns reasoning off on the wire."""
    if selection != _WIRE_NONE:
        return False
    provider = resolved.provider_config or {}
    mode_raw = provider.get("thinking_request_mode")
    mode: ThinkingRequestMode | None = mode_raw if isinstance(mode_raw, str) else None
    return mode in (THINKING_REQUEST_MODE_EXTRA_BODY, THINKING_REQUEST_MODE_REASONING_EFFORT)


def build_thinking_request_payload(
    selection: str,
    resolved: ResolvedModelConfig,
) -> dict[str, Any] | None:
    """Provider payload fragment for observability (not necessarily full extra_body)."""
    if not selection:
        return None

    provider = resolved.provider_config or {}
    mode_raw = provider.get("thinking_request_mode")
    mode: ThinkingRequestMode | None = mode_raw if isinstance(mode_raw, str) else None

    if mode is None or mode == THINKING_REQUEST_MODE_OMIT:
        return None
    if mode == THINKING_REQUEST_MODE_EXTRA_BODY:
        if selection == _WIRE_NONE:
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled", "effort": selection}}
    if mode == THINKING_REQUEST_MODE_REASONING_EFFORT:
        return {"reasoning_effort": selection}
    return None


def apply_thinking_to_chat_kwargs(
    kwargs: dict[str, Any],
    *,
    resolved: ResolvedModelConfig,
    thinking_effort: str,
) -> None:
    """Mutate ChatOpenAI kwargs for the selected thinking effort option value."""
    if not thinking_effort:
        return

    provider = resolved.provider_config or {}
    mode_raw = provider.get("thinking_request_mode")
    mode: ThinkingRequestMode | None = mode_raw if isinstance(mode_raw, str) else None

    if mode is None or mode == THINKING_REQUEST_MODE_OMIT:
        return

    if mode == THINKING_REQUEST_MODE_EXTRA_BODY:
        extra = dict(kwargs.get("extra_body") or {})
        if thinking_effort == _WIRE_NONE:
            extra["thinking"] = {"type": "disabled"}
        else:
            extra["thinking"] = {"type": "enabled"}
        kwargs["extra_body"] = extra
        return

    if mode == THINKING_REQUEST_MODE_REASONING_EFFORT:
        kwargs["reasoning_effort"] = thinking_effort
