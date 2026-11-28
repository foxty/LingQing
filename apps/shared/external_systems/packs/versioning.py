"""Pack identity and version comparison helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.shared.core.exceptions import ResourceNotFoundError

if TYPE_CHECKING:
    from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog


def pack_id_from_ref(pack_ref: str | None) -> str | None:
    if not pack_ref or not pack_ref.strip():
        return None
    at = pack_ref.find("@")
    if at == -1:
        return pack_ref.strip()
    return pack_ref[:at].strip()


def parse_semver(version: str) -> tuple[int, int, int] | None:
    parts = version.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def pack_version_is_behind(installed: str | None, catalog: str) -> bool:
    """Return True when ``catalog`` is newer than ``installed`` (or installed is unknown)."""
    if not installed or not installed.strip():
        return True
    if installed.strip() == catalog.strip():
        return False
    installed_parts = parse_semver(installed)
    catalog_parts = parse_semver(catalog)
    if installed_parts is None or catalog_parts is None:
        return installed.strip() != catalog.strip()
    return installed_parts < catalog_parts


def build_pack_operation_upstream_key(operation_id: str) -> str:
    from apps.shared.external_systems.api_connector.domain import ApiOperationDomain

    return ApiOperationDomain.build_pack_upstream_key(operation_id)


def pack_update_metadata(
    *,
    pack_ref: str | None,
    installed_pack_version: str | None,
    catalog: ApiConnectorPackCatalog | None = None,
) -> tuple[str | None, bool]:
    """Catalog semver and whether the bundled pack is newer than installed."""
    from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog

    pack_id = pack_id_from_ref(pack_ref)
    if not pack_id:
        return None, False
    catalog = catalog or ApiConnectorPackCatalog()
    try:
        manifest = catalog.get(pack_id)
    except ResourceNotFoundError:
        return None, False
    catalog_version = manifest.version
    return catalog_version, pack_version_is_behind(installed_pack_version, catalog_version)