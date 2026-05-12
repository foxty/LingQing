"""ModelBindingManager - handles model creation, binding, and cache invalidation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from apps.shared.infra.llm.llm_model_factory import LLMModelFactory
from apps.tenant_app_service.agents.agent_config import AgentConfig


@dataclass(frozen=True)
class _ModelBindingSignature:
    model_key: str
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    frequency_penalty: float | None
    loaded_skills: tuple[str, ...]
    tools: tuple[str, ...]


class ModelBindingManager:
    def __init__(self, agent_config: AgentConfig, logger, tenant_config: dict | None = None):
        self._agent_config = agent_config
        self._logger = logger
        self._tenant_config = tenant_config
        self._tenant_model_factory = LLMModelFactory(tenant_config) if tenant_config else None
        self._cached_model = None
        self._cached_signature: _ModelBindingSignature | None = None

    def invalidate(self) -> None:
        self._cached_model = None
        self._cached_signature = None

    def update_tenant_config(self, tenant_config: dict | None) -> None:
        """Update tenant config and invalidate cache if changed.

        Args:
            tenant_config: New tenant config dict from database
        """
        if tenant_config != self._tenant_config:
            self._tenant_config = tenant_config
            self._tenant_model_factory = LLMModelFactory(tenant_config) if tenant_config else None
            self.invalidate()
            self._logger.debug("Tenant config updated, cache invalidated")

    def get_or_create(
        self,
        model_key: str,
        loaded_skills: list[str],
        tools: list,
    ):
        """Get or create model with tools binding.

        Requires tenant LLM config to be configured.

        Args:
            model_key: Model key (unused, kept for compatibility)
            loaded_skills: List of loaded skill names
            tools: Pre-computed tools list.

        Returns:
            BaseChatModel with tools bound

        Raises:
            ValueError: If tenant LLM config is not configured
        """
        if not self._tenant_model_factory or not self._tenant_model_factory.is_configured():
            raise ValueError(
                "Tenant LLM config not configured for tenant. "
                "Please configure LLM in tenant settings before using agents."
            )

        skills = loaded_skills or []
        signature = self._build_signature(model_key, skills, tools)

        if self._cached_model is None or signature != self._cached_signature:
            model = self._tenant_model_factory.get_agent_model()
            self._logger.info(
                "Tenant model created for agent %s, tools=%s",
                self._agent_config.agent_name,
                [t.name for t in tools],
            )
            self._cached_model = model.bind_tools(tools)
            self._cached_signature = signature

        return self._cached_model

    def get_configured_model_id(self) -> str | None:
        """Return tenant-configured model_id used for LLM requests."""
        if not self._tenant_model_factory:
            return None
        return self._tenant_model_factory.get_agent_model_id()

    def get_max_output_tokens(self) -> int | None:
        """Return configured max output tokens for the main agent model."""
        if self._tenant_model_factory:
            max_tokens = self._tenant_model_factory.get_agent_max_output_tokens()
            if max_tokens is not None:
                return max_tokens
        return self._agent_config.max_tokens

    def _build_signature(
        self,
        model_key: str,
        loaded_skills: list[str],
        tools: Iterable,
    ) -> _ModelBindingSignature:
        tool_names = tuple(sorted(getattr(tool, "name", "") for tool in tools))
        return _ModelBindingSignature(
            model_key=model_key,
            temperature=self._agent_config.temperature,
            top_p=self._agent_config.top_p,
            max_tokens=self._agent_config.max_tokens,
            frequency_penalty=self._agent_config.frequency_penalty,
            loaded_skills=tuple(loaded_skills),
            tools=tool_names,
        )
