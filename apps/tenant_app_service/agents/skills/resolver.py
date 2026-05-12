"""Back-compat shim for ``agents.skills.resolver``.

The tool-list merge helper was renamed to
:mod:`apps.tenant_app_service.agents.skills.tool_resolver`. This module
re-exports ``resolve_effective_skill_tools`` so existing imports of
``apps.tenant_app_service.agents.skills.resolver`` keep working. New code
should import from the canonical location.
"""

from apps.tenant_app_service.agents.skills.tool_resolver import (
    resolve_effective_skill_tools,
)

__all__ = ["resolve_effective_skill_tools"]
