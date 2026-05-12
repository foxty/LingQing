"""Storage key resolution helpers for tenant-scoped file paths."""

from __future__ import annotations

from pathlib import Path

from apps.config import get_tenant_documents_path


def is_cloud_storage_ref(storage_ref: str) -> bool:
    return storage_ref.startswith("s3://")


def is_absolute_storage_ref(storage_ref: str) -> bool:
    return is_cloud_storage_ref(storage_ref) or Path(storage_ref).is_absolute()


def normalize_storage_key(tenant_id: int | str, storage_ref: str) -> str:
    """Persist tenant-relative storage keys; leave cloud refs unchanged."""
    if is_cloud_storage_ref(storage_ref):
        return storage_ref

    path = Path(storage_ref)
    if not path.is_absolute():
        return storage_ref.replace("\\", "/")

    tenant_root = Path(get_tenant_documents_path(tenant_id))
    try:
        return path.relative_to(tenant_root).as_posix()
    except ValueError:
        return storage_ref


def resolve_storage_ref(tenant_id: int | str, storage_key: str) -> str:
    """Resolve a persisted storage key to a concrete read/delete path."""
    if is_cloud_storage_ref(storage_key):
        return storage_key

    path = Path(storage_key)
    if path.is_absolute():
        return storage_key

    return str(Path(get_tenant_documents_path(tenant_id)) / storage_key)
