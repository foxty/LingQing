"""Skill configuration models and loaders.

This package provides runtime skill-loading building blocks for
skill resolution, prompt resolution, and tool-set resolution.

The ``SkillConfigLoader`` has moved to ``apps.tenant_app_service.skills.loader``
and ``resolve_effective_skill_tools`` lives in
``apps.tenant_app_service.agents.skills.tool_resolver``. The
back-compat shims at ``agents.skills.loader`` and
``agents.skills.resolver`` re-export them so existing imports keep
working; the package-level re-exports below are limited to types
that do not introduce an import cycle.
"""

from apps.tenant_app_service.agents.domain import SkillConfig, ToolConfig

__all__ = ["ToolConfig", "SkillConfig"]
