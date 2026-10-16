"""ModelBindingManager - handles model creation, binding, and cache invalidation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.llm_model_resolver import create_chat_model
from apps.shared.infra.llm.thinking import (
    DEFAULT_THINKING_EFFORT,
    ThinkingEffort,
    build_thinking_request_payload,
    coerce_thinking_effort,
    normalize_thinking_effort,
)
from apps.shared.llm_providers.service import LLMProviderConfigService
from apps.tenant_app_service.agents.agent_config import AgentConfig


@dataclass(frozen=True)
class _ModelBindingSignature:
    tenant_id: int
    cache_profile_id: int | None
    profile_updated_at: datetime | None
    provider_updated_at: datetime | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    frequency_penalty: float | None
    loaded_skills: tuple[str, ...]
    tools: tuple[str, ...]
    thinking_effort: ThinkingEffort


class ModelBindingManager:
    def __init__(self, agent_config: AgentConfig, logger):
        self._agent_config = agent_config
        self._logger = logger
        self._cached_model = None
        self._cached_signature: _ModelBindingSignature | None = None
        self._resolved_model_id: str | None = None
        self._resolved_profile_label: str | None = None
        self._resolved_max_tokens: int | None = None
        self._thinking_effort: ThinkingEffort = DEFAULT_THINKING_EFFORT
        self._thinking_requested_effort: ThinkingEffort = DEFAULT_THINKING_EFFORT
        self._thinking_supports = False
        self._thinking_request_payload: dict | None = None

    def invalidate(self) -> None:
        self._cached_model = None
        self._cached_signature = None
        self._resolved_model_id = None
        self._resolved_profile_label = None
        self._resolved_max_tokens = None
        self._thinking_effort = DEFAULT_THINKING_EFFORT
        self._thinking_requested_effort = DEFAULT_THINKING_EFFORT
        self._thinking_supports = False
        self._thinking_request_payload = None

    async def get_or_create(
        self,
        *,
        model_profile_id: int | None,
        loaded_skills: list[str],
        tools: list,
        tenant_id: int,
        db: AsyncSession,
        thinking_effort: ThinkingEffort | str | None = None,
    ):
        """Get or create model with tools binding using the tenant model registry."""
        skills = loaded_skills or []
        cache_profile_id = await self._resolve_cache_profile_id(
            model_profile_id=model_profile_id,
            tenant_id=tenant_id,
            db=db,
        )
        profile_updated_at: datetime | None = None
        provider_updated_at: datetime | None = None
        if cache_profile_id is not None:
            binding_service = LLMProviderConfigService(tenant_id, db)
            profile_updated_at, provider_updated_at = await binding_service.get_profile_binding_timestamps(
                cache_profile_id
            )
        effort = normalize_thinking_effort(thinking_effort)
        signature = self._build_signature(
            tenant_id=tenant_id,
            cache_profile_id=cache_profile_id,
            profile_updated_at=profile_updated_at,
            provider_updated_at=provider_updated_at,
            loaded_skills=skills,
            tools=tools,
            thinking_effort=effort,
        )

        if self._cached_model is not None and signature == self._cached_signature:
            return self._cached_model

        model = await self._create_model(
            model_profile_id=model_profile_id,
            tenant_id=tenant_id,
            db=db,
            thinking_effort=effort,
        )
        self._logger.info(
            "Tenant model created for agent %s profile=%s model_id=%s tools=%s",
            self._agent_config.agent_name,
            self._resolved_profile_label,
            self._resolved_model_id,
            [t.name for t in tools],
        )
        self._cached_model = model.bind_tools(tools)
        self._cached_signature = signature
        return self._cached_model

    async def _create_model(
        self,
        *,
        model_profile_id: int | None,
        tenant_id: int,
        db: AsyncSession,
        thinking_effort: ThinkingEffort,
    ):
        service = LLMProviderConfigService(tenant_id, db)
        resolved = await service.resolve_for_agent(model_profile_id, mini=False)
        self._thinking_requested_effort = normalize_thinking_effort(thinking_effort)
        effective_effort, supports = coerce_thinking_effort(thinking_effort, resolved)
        self._resolved_model_id = resolved.model_id
        self._resolved_profile_label = resolved.profile_name
        params = resolved.params or {}
        self._resolved_max_tokens = params.get("max_tokens")
        self._thinking_effort = effective_effort
        self._thinking_supports = supports
        self._thinking_request_payload = build_thinking_request_payload(effective_effort, resolved)
        return create_chat_model(resolved, thinking_effort=effective_effort)

    @staticmethod
    def _workbench_off_attempts_disable(payload: dict | None) -> bool:
        """True when observability payload shows workbench 'none' tried to disable reasoning."""
        if not isinstance(payload, dict):
            return False
        if payload.get("reasoning_effort") == "none":
            return True
        thinking = payload.get("thinking")
        return isinstance(thinking, dict) and thinking.get("type") == "disabled"

    def get_thinking_metrics_context(self) -> dict:
        return {
            "thinking_effort_requested": self._thinking_requested_effort,
            "thinking_effort": self._thinking_effort,
            "thinking_request": self._thinking_request_payload,
            "supports_thinking": self._thinking_supports,
            "thinking_effort_none_disables": self._workbench_off_attempts_disable(
                self._thinking_request_payload
            ),
        }

    def get_configured_model_id(self) -> str | None:
        return self._resolved_model_id

    def get_profile_label(self) -> str | None:
        return self._resolved_profile_label

    def get_max_output_tokens(self) -> int | None:
        if self._resolved_max_tokens is not None:
            return self._resolved_max_tokens
        return self._agent_config.max_tokens

    async def _resolve_cache_profile_id(
        self,
        *,
        model_profile_id: int | None,
        tenant_id: int,
        db: AsyncSession,
    ) -> int | None:
        """Resolve the profile id used for cache keys and model lookup."""
        if model_profile_id is not None:
            return model_profile_id

        service = LLMProviderConfigService(tenant_id, db)
        defaults = await service.get_defaults()
        return defaults.agent_profile_id

    def _build_signature(
        self,
        *,
        tenant_id: int,
        cache_profile_id: int | None,
        profile_updated_at: datetime | None,
        provider_updated_at: datetime | None,
        loaded_skills: list[str],
        tools: Iterable,
        thinking_effort: ThinkingEffort,
    ) -> _ModelBindingSignature:
        tool_names = tuple(sorted(getattr(tool, "name", "") for tool in tools))
        return _ModelBindingSignature(
            tenant_id=tenant_id,
            cache_profile_id=cache_profile_id,
            profile_updated_at=profile_updated_at,
            provider_updated_at=provider_updated_at,
            temperature=self._agent_config.temperature,
            top_p=self._agent_config.top_p,
            max_tokens=self._agent_config.max_tokens,
            frequency_penalty=self._agent_config.frequency_penalty,
            loaded_skills=tuple(loaded_skills),
            tools=tool_names,
            thinking_effort=thinking_effort,
        )
