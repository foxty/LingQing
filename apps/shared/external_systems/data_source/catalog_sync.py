"""Domain value object: catalog (metadata) sync login for per-user data sources.

Not a persisted entity — rules and parsing for the ``metadata_sync`` block on data-source config.
Lives beside ``domain.py`` (not inside it) to avoid a ``domain/`` package colliding with ``domain.py``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

METADATA_SYNC_CONFIG_KEY = "metadata_sync"


@dataclass(frozen=True)
class CatalogSyncCredentials:
    """Sync-login secrets used for discover/metadata jobs (not per-user query creds)."""

    username: str | None = None
    password: str | None = None

    @classmethod
    def from_block(cls, block: dict[str, Any] | None) -> CatalogSyncCredentials | None:
        """Parse the nested ``metadata_sync`` object (used by ``from_data_source_config``)."""
        if not isinstance(block, dict) or not block:
            return None
        username = (block.get("username") or block.get("user") or "").strip() or None
        password_raw = block.get("password")
        password = password_raw if isinstance(password_raw, str) and password_raw.strip() else None
        if not username and not password:
            return None
        return cls(username=username, password=password)

    @classmethod
    def from_data_source_config(cls, config: dict[str, Any] | None) -> CatalogSyncCredentials | None:
        block = (config or {}).get(METADATA_SYNC_CONFIG_KEY)
        return cls.from_block(block if isinstance(block, dict) else None)

    def is_configured_for(self, data_source_type: str) -> bool:
        password = (self.password or "").strip()
        if not password:
            return False
        ds_type = (data_source_type or "").lower()
        if ds_type == "databricks":
            return True
        username = (self.username or "").strip()
        return bool(username)

    @classmethod
    def is_configured_in_config(
        cls,
        config: dict[str, Any] | None,
        *,
        data_source_type: str | None = None,
    ) -> bool:
        sync = cls.from_data_source_config(config)
        if sync is None:
            return False
        return sync.is_configured_for(data_source_type or "")

    @classmethod
    def merge_connection_config(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Endpoint template + sync login secrets for metadata manager (drops nested block)."""
        merged = deepcopy(config)
        sync = cls.from_data_source_config(config)
        merged.pop(METADATA_SYNC_CONFIG_KEY, None)
        if sync is None:
            return merged
        if sync.username:
            merged["username"] = sync.username
        if sync.password:
            merged["password"] = sync.password
        return merged

    @classmethod
    def merge_incoming_into_config(
        cls,
        existing: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge admin PATCH payload; preserve stored secrets when client omits or sends placeholders."""
        from apps.shared.external_systems.data_source.sensitive_config import (
            DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS,
        )
        from apps.shared.utils.secret_merge import merge_dict_preserve_secrets

        return merge_dict_preserve_secrets(
            existing,
            incoming,
            sensitive_keys=DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS,
        )


def strip_user_mode_connection_template(data: dict[str, Any]) -> dict[str, Any]:
    """Domain: persisted template for user-mode sources — endpoint fields only, not shared login."""
    from apps.shared.external_systems.data_source.sensitive_config import (
        DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS,
    )

    strip_keys = frozenset(DATA_SOURCE_MERGE_SENSITIVE_LEAF_KEYS | {"username", "user", "connection_url"})
    cleaned = deepcopy(data)
    for key in list(cleaned.keys()):
        if key in strip_keys:
            del cleaned[key]
    return cleaned
