"""Context resource module — lightweight keyword search for @mention picker."""

from apps.shared.context_resource.domain import ContextResourceItem, ContextResourceKey
from apps.shared.context_resource.repository import ContextResourceRepository
from apps.shared.context_resource.service import ContextResourceSearchService

__all__ = [
    "ContextResourceItem",
    "ContextResourceKey",
    "ContextResourceRepository",
    "ContextResourceSearchService",
]
