"""Add runtime config JSON on LLM registry (provider + profile).

Revision ID: 077_llm_profile_runtime_config
Revises: 076_add_message_feedback
Create Date: 2026-10-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "077_llm_profile_runtime_config"
down_revision = "076_add_message_feedback"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    provider_cols = _column_names(inspector, "llm_providers")
    profile_cols = _column_names(inspector, "llm_model_profiles")

    if "config" not in provider_cols:
        if "provider_thinking_config" in provider_cols:
            op.alter_column("llm_providers", "provider_thinking_config", new_column_name="config")
        elif "wire_config" in provider_cols:
            op.alter_column("llm_providers", "wire_config", new_column_name="config")
        else:
            op.add_column("llm_providers", sa.Column("config", sa.JSON(), nullable=True))

    if "reasoning_config" not in profile_cols:
        op.add_column("llm_model_profiles", sa.Column("reasoning_config", sa.JSON(), nullable=True))

    from apps.shared.llm_providers.runtime_backfill import backfill_llm_registry_runtime_config

    backfill_llm_registry_runtime_config(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    profile_cols = _column_names(inspector, "llm_model_profiles")
    provider_cols = _column_names(inspector, "llm_providers")

    if "reasoning_config" in profile_cols:
        op.drop_column("llm_model_profiles", "reasoning_config")
    if "config" in provider_cols:
        op.drop_column("llm_providers", "config")
