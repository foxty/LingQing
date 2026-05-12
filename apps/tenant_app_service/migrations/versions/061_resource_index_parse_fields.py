"""Add parse lifecycle fields to resource_index.

Revision ID: 061_resource_index_parse_fields
Revises: 060_slack_channel_thread_mapping
"""

import sqlalchemy as sa
from alembic import op

revision = "061_resource_index_parse_fields"
down_revision = "060_slack_channel_thread_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resource_index",
        sa.Column("parse_job_id", sa.String(length=255), nullable=True, comment="External parse job id"),
    )
    op.add_column(
        "resource_index",
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True, comment="Last successful parse timestamp"),
    )
    op.add_column(
        "resource_index",
        sa.Column("parse_error", sa.Text(), nullable=True, comment="Last parse error message"),
    )
    op.add_column(
        "resource_index",
        sa.Column("parse_error_at", sa.DateTime(timezone=True), nullable=True, comment="Last parse failure timestamp"),
    )
    op.add_column(
        "resource_index",
        sa.Column(
            "parse_retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Document parse retry attempts",
        ),
    )
    op.create_index(
        "idx_resource_index_tenant_parse_job",
        "resource_index",
        ["tenant_id", "parse_job_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_resource_index_tenant_parse_job", table_name="resource_index")
    op.drop_column("resource_index", "parse_retry_count")
    op.drop_column("resource_index", "parse_error_at")
    op.drop_column("resource_index", "parse_error")
    op.drop_column("resource_index", "parsed_at")
    op.drop_column("resource_index", "parse_job_id")
