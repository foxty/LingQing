"""Domain value object: catalog (metadata) sync login for per-user data sources.

Not a persisted entity — rules and parsing for the ``metadata_sync`` block on data-source config.
Lives beside ``domain.py`` (not inside it) to avoid a ``domain/`` package colliding with ``domain.py``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

METADATA_SYNC_CONFIG_KEY = "metadata_sync"
# API contract: GET responses redact secrets to this token; PATCH may echo it to mean "keep stored value".
API_SECRET_PLACEHOLDER = "***"


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
        if password == API_SECRET_PLACEHOLDER:
            password = None
        if not username and not password:
            return None
        return cls(username=username, password=password)

    @classmethod
    def from_data_source_config(cls, config: dict[str, Any] | None) -> CatalogSyncCredentials | None:
        block = (config or {}).get(METADATA_SYNC_CONFIG_KEY)
        return cls.from_block(block if isinstance(block, dict) else None)

    def is_configured_for(self, data_source_type: str) -> bool:
        password = (self.password or "").strip()
        if not password or password == API_SECRET_PLACEHOLDER:
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
        """Merge admin PATCH payload; preserve stored sync password when client sends placeholder."""
        base = deepcopy(existing or {})
        if not incoming:
            return base
        merged = {**base, **incoming}
        root_pwd = incoming.get("password")
        if root_pwd in (None, "", API_SECRET_PLACEHOLDER) and base.get("password"):
            merged["password"] = base["password"]
        new_block = incoming.get(METADATA_SYNC_CONFIG_KEY)
        if not isinstance(new_block, dict) or not new_block:
            return merged
        prev_dict = (
            (base.get(METADATA_SYNC_CONFIG_KEY) or {})
            if isinstance(base.get(METADATA_SYNC_CONFIG_KEY), dict)
            else {}
        )
        combined_sync = {**prev_dict, **new_block}
        pwd = new_block.get("password")
        if pwd in (None, "", API_SECRET_PLACEHOLDER) and prev_dict.get("password"):
            combined_sync["password"] = prev_dict["password"]
        merged[METADATA_SYNC_CONFIG_KEY] = combined_sync
        return merged


def strip_user_mode_connection_template(data: dict[str, Any]) -> dict[str, Any]:
    """Domain: persisted template for user-mode sources — endpoint fields only, not shared login."""
    from apps.shared.utils.field_cipher import SENSITIVE_FIELD_KEYS

    strip_keys = frozenset(SENSITIVE_FIELD_KEYS | {"username", "user", "connection_url"})
    cleaned = deepcopy(data)
    for key in list(cleaned.keys()):
        if key in strip_keys:
            del cleaned[key]
    return cleaned
