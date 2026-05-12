"""Initial database schema.

Revision ID: 001
Revises:
Create Date: 2025-12-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "slug",
            sa.String(length=100),
            nullable=True,
            comment="URL-friendly identifier for tenant",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tenant_name"),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
    )
    op.create_index("idx_tenants_status", "tenants", ["status"])

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("idx_users_tenant_id", "users", ["tenant_id"])
    op.create_index("idx_users_status", "users", ["status"])
    op.create_index("ix_users_username", "users", ["username"])

    # Create agents table
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("example_questions", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agents_tenant_id", "agents", ["tenant_id"])
    op.create_index("idx_agents_status", "agents", ["status"])

    # Create data_sources table
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "type",
            sa.String(length=50),
            nullable=False,
            comment="sqlite, postgres, mysql, databricks, etc.",
        ),
        sa.Column(
            "managed",
            sa.Boolean(),
            server_default="1",
            nullable=False,
            comment="Whether this data source is managed by the platform",
        ),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_datasource_tenant_name"),
    )

    # Create documents table (without chunk_count, with vector_ref_id)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("file_url", sa.String(length=1000), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "vector_ref_id",
            sa.String(length=36),
            nullable=True,
            comment="Vector reference ID (UUID) for RAG retrieval",
        ),
        sa.Column("status", sa.String(length=20), server_default="processing", nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column(
            "upload_date",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_file_hash", "documents", ["file_hash"])
    op.create_index("idx_documents_uploaded_by", "documents", ["uploaded_by"])
    op.create_index("ix_documents_vector_ref_id", "documents", ["vector_ref_id"], unique=True)

    # Create asset_metadata table (with vector_ref_id)
    op.create_table(
        "asset_metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("asset_name", sa.String(length=200), nullable=False),
        sa.Column(
            "asset_type",
            sa.String(length=50),
            server_default="table",
            nullable=False,
            comment="table, view, materialized_view, api_endpoint",
        ),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("source_info", sa.JSON(), nullable=False),
        sa.Column(
            "vector_ref_id",
            sa.String(length=36),
            nullable=True,
            comment="Vector reference ID (UUID) for RAG retrieval",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", "asset_name", name="uq_asset_datasource_name"),
    )
    op.create_index("ix_asset_metadata_vector_ref_id", "asset_metadata", ["vector_ref_id"], unique=True)

    # Create data_sources indexes
    op.create_index("idx_data_sources_tenant_id", "data_sources", ["tenant_id"])

    # Create asset_metadata indexes (already created above)

    # Create temp_table_metadata table for workspace management
    op.create_table(
        "temp_table_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "thread_id",
            sa.String(length=100),
            nullable=False,
            comment="Thread ID (format: {tenant_id}_{user_id}_{agent_id})",
        ),
        sa.Column(
            "data_source_id",
            sa.Integer(),
            nullable=False,
            comment="Always points to tenant's Analytics DB",
        ),
        sa.Column("table_name", sa.String(length=200), nullable=False),
        sa.Column(
            "meta_info",
            sa.JSON(),
            nullable=False,
            comment="Additional metadata: source info, query, columns, etc.",
        ),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False,
            comment="Expiration time for automatic cleanup",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "table_name",
            name="uq_temp_table_ds_name",
        ),
    )
    op.create_index("ix_temp_table_metadata_thread_id", "temp_table_metadata", ["thread_id"])
    op.create_index("ix_temp_table_metadata_expires_at", "temp_table_metadata", ["expires_at"])
    op.create_index(
        "idx_temp_table_tenant_thread",
        "temp_table_metadata",
        ["tenant_id", "thread_id"],
    )

    # Add asset_count column to data_sources
    op.add_column(
        "data_sources",
        sa.Column("asset_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Create agent_metrics_events table
    op.create_table(
        "agent_metrics_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("input_size", sa.Integer(), nullable=True),
        sa.Column("output_size", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("extra_context", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("idx_events_agent_time", "agent_metrics_events", ["agent_id", "timestamp"])
    op.create_index("idx_events_session_id", "agent_metrics_events", ["session_id"])
    op.create_index("idx_events_tenant_time", "agent_metrics_events", ["tenant_id", "timestamp"])
    op.create_index("idx_events_thread_id", "agent_metrics_events", ["thread_id"])
    op.create_index("idx_events_user_time", "agent_metrics_events", ["user_id", "timestamp"])

    # Create vector_sync_status table
    op.create_table(
        "vector_sync_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("sync_type", sa.String(length=50), nullable=False, comment="documents or assets"),
        sa.Column(
            "last_sync_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_sync_status",
            sa.String(length=20),
            nullable=False,
            server_default="success",
            comment="success, failed, or partial",
        ),
        sa.Column(
            "sync_counter",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Incremental sync count",
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(),
            nullable=True,
            comment="Last consistency verification timestamp",
        ),
        sa.Column(
            "inconsistency_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Historical inconsistency count",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sync_type", name="uq_vector_sync_tenant_type"),
    )
    op.create_index(
        "idx_vector_sync_tenant_type",
        "vector_sync_status",
        ["tenant_id", "sync_type"],
    )

    # Create chat_threads table
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "summary_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of thread summaries",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_threads_tenant_user", "chat_threads", ["tenant_id", "user_id"])
    op.create_index("idx_chat_threads_updated_at", "chat_threads", ["updated_at"])

    # Create chat_messages table
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Database record ID"),
        sa.Column(
            "message_id",
            sa.String(length=255),
            nullable=True,
            comment="LangChain message ID for deduplication",
        ),
        sa.Column(
            "thread_id",
            sa.String(length=255),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=50), nullable=False, comment="human, ai, tool, system, summary"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "is_summarized",
            sa.Boolean(),
            nullable=False,
            server_default="0",
            comment="Whether this message has been summarized",
        ),
        sa.Column("additional_kwargs", sa.JSON(), nullable=True, comment="LangChain message metadata"),
        sa.Column(
            "message_metadata",
            sa.JSON(),
            nullable=True,
            comment="System metadata: visibility, capability context, message grouping",
        ),
        sa.Column(
            "tool_calls",
            sa.JSON(),
            nullable=True,
            comment="Structured tool call data (LangChain parsed format)",
        ),
        sa.Column(
            "session_id",
            sa.String(255),
            nullable=True,
            comment="Customized session ID for session tracking",
        ),
        sa.Column(
            "agent_id",
            sa.Integer(),
            nullable=True,
            comment="Current agent executing this message",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_chat_messages_message_id"),
    )
    op.create_index("idx_chat_messages_thread_created", "chat_messages", ["thread_id", "created_at"])
    op.create_index("idx_chat_messages_thread_summarized", "chat_messages", ["thread_id", "is_summarized"])
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index(
        "idx_chat_messages_thread_created_id",
        "chat_messages",
        ["thread_id", "created_at", "id"],
    )
    op.create_index(
        "idx_chat_messages_thread_type_created",
        "chat_messages",
        ["thread_id", "type", "created_at", "id"],
    )
    op.create_index(
        "idx_chat_messages_agent_session",
        "chat_messages",
        ["agent_id", "session_id"],
    )

    # Create session_summaries table
    op.create_table(
        "session_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False, comment="Unique session ID"),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_intent", sa.Text(), nullable=False, comment="User's intent in this session"),
        sa.Column(
            "tools_used",
            sa.JSON(),
            nullable=False,
            comment="List of tools used in this session",
        ),
        sa.Column("key_results", sa.Text(), nullable=False, comment="Key results summary"),
        sa.Column(
            "summary_text",
            sa.Text(),
            nullable=True,
            comment="Optional detailed summary generated by LLM",
        ),
        sa.Column(
            "message_range",
            sa.JSON(),
            nullable=False,
            comment="Message time range: {from_time, to_time, count}",
        ),
        sa.Column(
            "included_in_thread_summary",
            sa.Boolean(),
            nullable=False,
            server_default="0",
            comment="Whether this session has been included in a thread summary",
        ),
        sa.Column(
            "thread_summary_version",
            sa.Integer(),
            nullable=True,
            comment="Thread summary version that includes this session",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_session_summaries_thread", "session_summaries", ["thread_id", "created_at"])
    op.create_index("idx_session_summaries_session", "session_summaries", ["session_id"], unique=True)
    op.create_index(
        "idx_session_summaries_thread_summarized",
        "session_summaries",
        ["thread_id", "included_in_thread_summary"],
    )
    op.create_index("session_summaries_tenant_id", "session_summaries", ["tenant_id"])

    # Create thread_summaries table
    op.create_table(
        "thread_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="Summary version, incremented for each new summary",
        ),
        sa.Column("summary_content", sa.Text(), nullable=False, comment="Thread summary text"),
        sa.Column(
            "session_range",
            sa.JSON(),
            nullable=False,
            comment="Session range: {from_session_id, to_session_id, session_count}",
        ),
        sa.Column(
            "message_range",
            sa.JSON(),
            nullable=False,
            comment="Message time range: {from_time, to_time, count}",
        ),
        sa.Column("session_count", sa.Integer(), nullable=False, comment="Number of sessions covered"),
        sa.Column(
            "token_count_before",
            sa.Integer(),
            nullable=False,
            comment="Total tokens before summarization",
        ),
        sa.Column(
            "token_count_after",
            sa.Integer(),
            nullable=False,
            comment="Token count of the summary itself",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_thread_summaries_thread_version", "thread_summaries", ["thread_id", "version"])
    op.create_index("idx_thread_summaries_created", "thread_summaries", ["created_at"])
    op.create_index("thread_summaries_thread_id", "thread_summaries", ["thread_id"])
    op.create_index("thread_summaries_tenant_id", "thread_summaries", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("thread_summaries")
    op.drop_table("session_summaries")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
    op.drop_table("vector_sync_status")
    op.drop_table("agent_metrics_events")
    op.drop_column("data_sources", "asset_count")
    op.drop_table("temp_table_metadata")
    op.drop_table("stats_aggregates")
    op.drop_table("asset_metadata")
    op.drop_table("documents")
    op.drop_table("data_sources")
    op.drop_table("agents")
    op.drop_table("users")
    op.drop_table("tenants")
