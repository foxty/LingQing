"""Back-compat shim.

``SkillConfigLoader`` has moved to ``apps.tenant_app_service.skills.loader``.
This module re-exports the same symbol so existing imports of
``apps.tenant_app_service.agents.skills.loader.SkillConfigLoader`` keep
working. New code should import from the canonical location.
"""

from apps.tenant_app_service.skills.loader import SkillConfigLoader

__all__ = ["SkillConfigLoader"]
