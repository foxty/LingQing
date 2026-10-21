"""Shared threads: kind, memberships, message authors, ingress mirror flags.

Ingress backfill: only Slack channel thread anchors (non-empty
``ingress_thread_links.external_thread_key``) become shared; DMs keep
``thread_kind=personal`` and ``passive_mirror_enabled=false``.

Roster backfill (Option B): every ``chat_threads`` row gets owner + primary
agent membership rows so personal and shared use the same tables.

Revision ID: 079_shared_threads
Revises: 078_add_charts_table
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "079_shared_threads"
down_revision = "078_add_charts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_threads",
        sa.Column(
            "thread_kind",
            sa.String(length=20),
            nullable=False,
            server_default="personal",
            comment="personal | shared",
        ),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="Human author for shared/ingress messages",
        ),
    )
    op.create_index("idx_chat_messages_author", "chat_messages", ["author_user_id"])

    op.create_table(
        "chat_thread_user_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "thread_id",
            sa.String(length=255),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "user_id", name="uq_chat_thread_user_member"),
    )
    op.create_index("idx_chat_thread_user_members_tenant", "chat_thread_user_members", ["tenant_id"])
    op.create_index("idx_chat_thread_user_members_user", "chat_thread_user_members", ["tenant_id", "user_id"])

    op.create_table(
        "chat_thread_agent_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "thread_id",
            sa.String(length=255),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("display_alias", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "agent_id", name="uq_chat_thread_agent_member"),
    )
    op.create_index("idx_chat_thread_agent_members_tenant", "chat_thread_agent_members", ["tenant_id"])

    op.add_column(
        "ingress_thread_links",
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="slack"),
    )
    op.add_column(
        "ingress_thread_links",
        sa.Column(
            "passive_mirror_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ingress_thread_links",
        sa.Column("link_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )

    # Slack DMs use empty external_thread_key; channel thread anchors use a non-empty key.
    op.execute(
        """
        UPDATE ingress_thread_links
        SET passive_mirror_enabled = false
        WHERE external_thread_key = ''
        """
    )

    # Ingress-linked channel thread anchors become shared threads with owner membership.
    op.execute(
        """
        UPDATE chat_threads ct
        SET thread_kind = 'shared'
        FROM ingress_thread_links itl
        WHERE itl.chat_thread_id = ct.id
          AND ct.thread_kind = 'personal'
          AND itl.external_thread_key <> ''
        """
    )
    op.execute(
        """
        INSERT INTO chat_thread_user_members (tenant_id, thread_id, user_id, role)
        SELECT ct.tenant_id, ct.id, ct.user_id, 'owner'
        FROM chat_threads ct
        INNER JOIN ingress_thread_links itl ON itl.chat_thread_id = ct.id
        WHERE itl.external_thread_key <> ''
        ON CONFLICT ON CONSTRAINT uq_chat_thread_user_member DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO chat_thread_agent_members (tenant_id, thread_id, agent_id)
        SELECT DISTINCT ct.tenant_id, itl.chat_thread_id, itl.agent_id
        FROM ingress_thread_links itl
        INNER JOIN chat_threads ct ON ct.id = itl.chat_thread_id
        WHERE itl.external_thread_key <> ''
        ON CONFLICT ON CONSTRAINT uq_chat_thread_agent_member DO NOTHING
        """
    )

    # All threads: owner + primary agent on roster (personal = 1+1).
    op.execute(
        """
        INSERT INTO chat_thread_user_members (tenant_id, thread_id, user_id, role)
        SELECT ct.tenant_id, ct.id, ct.user_id, 'owner'
        FROM chat_threads ct
        WHERE NOT EXISTS (
            SELECT 1 FROM chat_thread_user_members m
            WHERE m.thread_id = ct.id AND m.user_id = ct.user_id
        )
        ON CONFLICT ON CONSTRAINT uq_chat_thread_user_member DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO chat_thread_agent_members (tenant_id, thread_id, agent_id)
        SELECT ct.tenant_id, ct.id, ct.agent_id
        FROM chat_threads ct
        WHERE NOT EXISTS (
            SELECT 1 FROM chat_thread_agent_members a
            WHERE a.thread_id = ct.id AND a.agent_id = ct.agent_id
        )
        ON CONFLICT ON CONSTRAINT uq_chat_thread_agent_member DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("ingress_thread_links", "link_metadata")
    op.drop_column("ingress_thread_links", "passive_mirror_enabled")
    op.drop_column("ingress_thread_links", "platform")
    op.drop_table("chat_thread_agent_members")
    op.drop_table("chat_thread_user_members")
    op.drop_index("idx_chat_messages_author", table_name="chat_messages")
    op.drop_column("chat_messages", "author_user_id")
    op.drop_column("chat_threads", "thread_kind")
