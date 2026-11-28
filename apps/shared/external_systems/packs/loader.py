"""Load and validate API connector pack manifests from the repository."""

from __future__ import annotations

from pathlib import Path

import yaml

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.external_systems.packs.schemas import ApiConnectorPackManifest

DEFAULT_PACK_DIRECTORY = Path(__file__).resolve().parents[4] / "config" / "integration-packs" / "api_connector"


class ApiConnectorPackCatalog:
    """Filesystem catalog; structurally implements ``IntegrationPackCatalog[ApiConnectorPackManifest]``."""
    def __init__(self, pack_directory: Path | None = None) -> None:
        self._directory = pack_directory or DEFAULT_PACK_DIRECTORY

    def list(self) -> list[ApiConnectorPackManifest]:
        if not self._directory.exists():
            return []
        manifests = [self._load_path(path) for path in sorted(self._directory.glob("*.yaml"))]
        pack_ids = [manifest.pack_id for manifest in manifests]
        if len(pack_ids) != len(set(pack_ids)):
            raise ValidationError("API connector pack catalog contains duplicate pack_id values")
        return manifests

    def get(self, pack_id: str) -> ApiConnectorPackManifest:
        for manifest in self.list():
            if manifest.pack_id == pack_id:
                return manifest
        raise ResourceNotFoundError(f"API connector pack not found: {pack_id}")

    @staticmethod
    def _load_path(path: Path) -> ApiConnectorPackManifest:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            return ApiConnectorPackManifest.model_validate(raw)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            raise ValidationError(f"Invalid API connector pack manifest: {path.name}") from exc
