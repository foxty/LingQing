"""ModelBindingManager - handles model creation, binding, and cache invalidation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.llm_model_resolver import create_chat_model
from apps.shared.llm_providers.service import LLMProviderConfigService
from apps.tenant_app_service.agents.agent_config import AgentConfig


@dataclass(frozen=True)
class _ModelBindingSignature:
    model_profile_id: int | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    frequency_penalty: float | None
    loaded_skills: tuple[str, ...]
    tools: tuple[str, ...]


class ModelBindingManager:
    def __init__(self, agent_config: AgentConfig, logger):
        self._agent_config = agent_config
        self._logger = logger
        self._cached_model = None
        self._cached_signature: _ModelBindingSignature | None = None
        self._resolved_model_id: str | None = None
        self._resolved_profile_label: str | None = None
        self._resolved_max_tokens: int | None = None

    def invalidate(self) -> None:
        self._cached_model = None
        self._cached_signature = None
        self._resolved_model_id = None
        self._resolved_profile_label = None
        self._resolved_max_tokens = None

    async def get_or_create(
        self,
        *,
        model_profile_id: int | None,
        loaded_skills: list[str],
        tools: list,
        tenant_id: int,
        db: AsyncSession,
    ):
        """Get or create model with tools binding using the tenant model registry."""
        skills = loaded_skills or []
        signature = self._build_signature(model_profile_id, skills, tools)

        if self._cached_model is not None and signature == self._cached_signature:
            return self._cached_model

        model = await self._create_model(
            model_profile_id=model_profile_id,
            tenant_id=tenant_id,
            db=db,
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
    ):
        service = LLMProviderConfigService(tenant_id, db)
        resolved = await service.resolve_for_agent(model_profile_id, mini=False)
        self._resolved_model_id = resolved.model_id
        self._resolved_profile_label = resolved.profile_name
        params = resolved.params or {}
        self._resolved_max_tokens = params.get("max_tokens")
        return create_chat_model(resolved)

    def get_configured_model_id(self) -> str | None:
        return self._resolved_model_id

    def get_profile_label(self) -> str | None:
        return self._resolved_profile_label

    def get_max_output_tokens(self) -> int | None:
        if self._resolved_max_tokens is not None:
            return self._resolved_max_tokens
        return self._agent_config.max_tokens

    def _build_signature(
        self,
        model_profile_id: int | None,
        loaded_skills: list[str],
        tools: Iterable,
    ) -> _ModelBindingSignature:
        tool_names = tuple(sorted(getattr(tool, "name", "") for tool in tools))
        return _ModelBindingSignature(
            model_profile_id=model_profile_id,
            temperature=self._agent_config.temperature,
            top_p=self._agent_config.top_p,
            max_tokens=self._agent_config.max_tokens,
            frequency_penalty=self._agent_config.frequency_penalty,
            loaded_skills=tuple(loaded_skills),
            tools=tool_names,
        )
