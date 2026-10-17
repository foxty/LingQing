"""One-shot DB backfill for LLM registry runtime JSON (migration / ops)."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from apps.shared.db.models import LLMModelProfile, LLMProvider
from apps.shared.llm_providers.domain import LLMModelProfileDomain, ModelProfileCategory, ModelProfileSource
from apps.shared.llm_providers.runtime_config import (
    seed_params_from_catalog,
    seed_provider_config_from_catalog,
    seed_reasoning_config_from_catalog,
)

_NOW = datetime.now(UTC)


def _preset_key(raw: str | None) -> str | None:
    if not raw:
        return None
    stripped = raw.strip()
    return stripped or None


def _json_snapshot_missing(value: object | None) -> bool:
    """True when runtime JSON was never materialized (SQL NULL or JSON null)."""
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() == "null"


def backfill_llm_registry_runtime_config(connection: sa.Connection) -> None:
    """Populate llm_providers.config and profile params/reasoning_config from catalog."""
    provider_rows = connection.execute(
        sa.text("SELECT id, preset_key, config FROM llm_providers")
    ).fetchall()
    for row in provider_rows:
        if not _json_snapshot_missing(row.config):
            continue
        cfg = seed_provider_config_from_catalog(_preset_key(row.preset_key))
        if cfg is not None:
            connection.execute(
                sa.update(LLMProvider).where(LLMProvider.id == row.id).values(config=cfg)
            )

    profile_rows = connection.execute(
        sa.text(
            """
            SELECT
                p.id,
                p.tenant_id,
                p.provider_id,
                p.name,
                p.category,
                p.model_id,
                p.params,
                p.reasoning_config,
                p.catalog_model_key,
                p.source,
                lp.preset_key AS provider_preset_key
            FROM llm_model_profiles p
            INNER JOIN llm_providers lp ON lp.id = p.provider_id
            """
        )
    ).fetchall()

    for row in profile_rows:
        preset_key = _preset_key(row.provider_preset_key)
        category = ModelProfileCategory(row.category)
        needs_params = _json_snapshot_missing(row.params)
        needs_reasoning = category == ModelProfileCategory.LLM and _json_snapshot_missing(row.reasoning_config)
        if not needs_params and not needs_reasoning:
            continue

        domain = LLMModelProfileDomain(
            id=row.id,
            tenant_id=row.tenant_id,
            provider_id=row.provider_id,
            name=row.name,
            category=category,
            model_id=row.model_id,
            params=row.params,
            reasoning_config=row.reasoning_config,
            catalog_model_key=row.catalog_model_key,
            source=ModelProfileSource(row.source),
            created_at=_NOW,
            updated_at=_NOW,
        )

        params = row.params if not needs_params else None
        if needs_params:
            params = seed_params_from_catalog(domain, provider_preset_key=preset_key)

        reasoning_config = row.reasoning_config if not needs_reasoning else None
        if needs_reasoning:
            reasoning_config = seed_reasoning_config_from_catalog(domain, provider_preset_key=preset_key)

        connection.execute(
            sa.update(LLMModelProfile)
            .where(LLMModelProfile.id == row.id)
            .values(params=params, reasoning_config=reasoning_config)
        )
