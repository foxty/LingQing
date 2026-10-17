"""One-shot runtime JSON backfill (migration 077)."""

import json

import sqlalchemy as sa
from sqlalchemy import create_engine

from apps.shared.db.models import Base, LLMModelProfile, LLMProvider, Tenant
from apps.shared.llm_providers.runtime_backfill import backfill_llm_registry_runtime_config
from apps.shared.llm_providers.runtime_config import seed_provider_config_from_catalog


def test_backfill_populates_legacy_null_runtime_columns():
    """Sync path matches Alembic op.get_bind() (not async session run_sync)."""
    assert seed_provider_config_from_catalog("bailian") is not None
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            sa.insert(Tenant).values(
                id=1,
                name="backfill-tenant",
                slug="backfill-tenant",
                status="active",
                config=json.dumps({}),
            )
        )
        conn.execute(
            sa.insert(LLMProvider).values(
                id=1,
                tenant_id=1,
                display_name="Legacy Bailian",
                preset_key="bailian",
                type="openai-compatible",
                api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key_encrypted="enc",
                status="active",
            )
        )
        conn.execute(
            sa.insert(LLMModelProfile).values(
                id=1,
                tenant_id=1,
                provider_id=1,
                name="Legacy Qwen",
                category="llm",
                model_id="qwen3.5-plus",
                catalog_model_key="bailian/qwen3.5-plus",
                source="preset",
            )
        )
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM llm_providers WHERE config IS NULL")).scalar() == 1
        )
        backfill_llm_registry_runtime_config(conn)
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM llm_providers WHERE config IS NULL")).scalar() == 0
        )

        provider_cfg = conn.execute(
            sa.text("SELECT config FROM llm_providers WHERE id = 1")
        ).scalar_one()
        profile_row = conn.execute(
            sa.text("SELECT params, reasoning_config FROM llm_model_profiles WHERE id = 1")
        ).one()

    assert provider_cfg is not None
    if isinstance(provider_cfg, str):
        provider_cfg = json.loads(provider_cfg)
    assert provider_cfg.get("thinking_request_mode") == "extra_body_thinking"
    assert profile_row.params is not None
    assert profile_row.reasoning_config is not None
    reasoning = profile_row.reasoning_config
    if isinstance(reasoning, str):
        reasoning = json.loads(reasoning)
    assert reasoning.get("supports_thinking") is True
