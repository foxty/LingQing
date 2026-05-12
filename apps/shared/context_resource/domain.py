"""Context resource domain — lightweight keyword search across all resource types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextResourceKey:
    """Stable reference to a context-capable resource (type + primary key)."""

    resource_type: str
    resource_id: int


@dataclass(frozen=True)
class ContextResourceItem:
    """A single hit from the context resource keyword search.

    Attributes:
        resource_type: Canonical type string (document, dashboard, report,
            scheduled_task, app, asset, api_connector).
        resource_id: Primary key of the underlying resource.
        title: Human-readable display name.
        subtitle: Optional secondary label (e.g. data source name, owner).
    """

    resource_type: str
    resource_id: int
    title: str
    subtitle: str | None = None

    def to_metadata_dict(self) -> dict[str, Any]:
        """Serialize for chat message_metadata.context_resources."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "title": self.title,
            "subtitle": self.subtitle,
        }
