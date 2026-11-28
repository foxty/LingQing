"""Integration pack catalog port (filesystem and future backends implement this shape)."""

from __future__ import annotations

from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class IntegrationPackCatalog(Protocol[T_co]):
    """Load integration pack manifests by pack_id without tenant persistence."""

    def list(self) -> list[T_co]: ...

    def get(self, pack_id: str) -> T_co: ...