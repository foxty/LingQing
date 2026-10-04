"""Database ORM models."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Tenant(Base):
    """Tenant model."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    slug: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, comment="URL-friendly identifier for tenant"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    force_sso: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="When true, native password login is rejected except for break-glass admins",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    agents: Mapped[list["Agent"]] = relationship("Agent", back_populates="tenant", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="tenant", cascade="all, delete-orphan"
    )
    document_collections: Mapped[list["DocumentCollection"]] = relationship(
        "DocumentCollection", back_populates="tenant", cascade="all, delete-orphan"
    )
    data_sources: Mapped[list["DataSource"]] = relationship(
        "DataSource", back_populates="tenant", cascade="all, delete-orphan"
    )
    dashboards: Mapped[list["Dashboard"]] = relationship(
        "Dashboard", back_populates="tenant", cascade="all, delete-orphan"
    )
    live_apps: Mapped[list["LiveApp"]] = relationship("LiveApp", back_populates="tenant", cascade="all, delete-orphan")
    api_connectors: Mapped[list["ApiConnector"]] = relationship(
        "ApiConnector", back_populates="tenant", cascade="all, delete-orphan"
    )
    llm_providers: Mapped[list["LLMProvider"]] = relationship(
        "LLMProvider", back_populates="tenant", cascade="all, delete-orphan"
    )
    llm_model_profiles: Mapped[list["LLMModelProfile"]] = relationship(
        "LLMModelProfile", back_populates="tenant", cascade="all, delete-orphan"
    )


class User(Base):
    """User model."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users", lazy="noload")
    memberships: Mapped[list["TenantMembership"]] = relationship(
        "TenantMembership",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    credentials: Mapped["UserCredential"] = relationship(
        "UserCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="noload",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="owner_user", foreign_keys="Document.owner_id"
    )
    created_live_apps: Mapped[list["LiveApp"]] = relationship(
        "LiveApp",
        back_populates="owner_user",
        foreign_keys="LiveApp.owner_id",
        lazy="noload",
    )


class TenantMembership(Base):
    """Tenant membership for users (tenant isolation)."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    is_break_glass: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Allows native password login even when tenant.force_sso is enabled",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")
    user: Mapped["User"] = relationship("User", back_populates="memberships", lazy="noload")


class UserCredential(Base):
    """User credentials for native identity."""

    __tablename__ = "user_credentials"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_credentials_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_reset_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="credentials", lazy="noload")


class AuditEvent(Base):
    """Audit events for auth & provisioning changes."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("idx_audit_events_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AuthProvider(Base):
    """Per-tenant identity provider configuration (OIDC in v1)."""

    __tablename__ = "auth_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "display_name", name="uq_auth_provider_tenant_display"),
        Index("idx_auth_providers_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False, default="oidc", server_default="oidc")
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    identity_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("identity_sources.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")


class IdentitySource(Base):
    """Neutral anchor for external identity bindings (OIDC providers, channel workspaces)."""

    __tablename__ = "identity_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_key", name="uq_identity_source_tenant_key"),
        Index("idx_identity_sources_tenant_kind", "tenant_id", "source_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bind_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="reject_unknown", server_default="reject_unknown"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")
    external_identities: Mapped[list["ExternalIdentity"]] = relationship(
        "ExternalIdentity",
        back_populates="identity_source",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class TenantLoginDomain(Base):
    """Email domain claimed by a tenant for resolver routing. Globally unique domain."""

    __tablename__ = "tenant_login_domains"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_tenant_login_domain"),
        Index("idx_tenant_login_domains_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")


class ExternalIdentity(Base):
    """Binding from an external subject to an internal user. Many identities per user."""

    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "identity_source_id",
            "external_subject",
            name="uq_external_identity_subject",
        ),
        Index("idx_external_identities_tenant_user", "tenant_id", "user_id"),
        Index("idx_external_identities_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    identity_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("identity_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    identity_source: Mapped["IdentitySource"] = relationship(
        "IdentitySource", back_populates="external_identities", lazy="noload"
    )
    user: Mapped["User | None"] = relationship("User", lazy="noload")


class SsoLoginState(Base):
    """Short-lived PKCE state/nonce for an in-flight OIDC login."""

    __tablename__ = "sso_login_states"
    __table_args__ = (
        UniqueConstraint("state", name="uq_sso_login_state"),
        Index("idx_sso_login_states_expiry", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("auth_providers.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class SsoLoginTicket(Base):
    """One-time ticket exchanged by the portal for an internal JWT after callback."""

    __tablename__ = "sso_login_tickets"
    __table_args__ = (
        UniqueConstraint("ticket", name="uq_sso_login_ticket"),
        Index("idx_sso_login_tickets_expiry", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ticket: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Agent(Base):
    """Agent model."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="Unified owner field for ACL/ABAC"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    example_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="agents", lazy="noload")


class ChatThread(Base):
    """Chat thread model for conversation management."""

    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    summary_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="Number of thread summaries"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")
    user: Mapped["User"] = relationship("User", lazy="noload")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="thread",
        order_by="(ChatMessage.created_at, ChatMessage.id)",
        cascade="all, delete-orphan",
    )
    thread_summaries: Mapped[list["ThreadSummary"]] = relationship(
        "ThreadSummary",
        back_populates="thread",
        order_by="ThreadSummary.version.desc()",
        cascade="all, delete-orphan",
    )
    session_summaries: Mapped[list["SessionSummary"]] = relationship(
        "SessionSummary",
        back_populates="thread",
        order_by="SessionSummary.created_at.desc()",
        cascade="all, delete-orphan",
    )
    artifact_links: Mapped[list["ArtifactLink"]] = relationship(
        "ArtifactLink",
        back_populates="thread",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class ChatMessage(Base):
    """Individual chat message within a thread.

    Stores messages independently for efficient querying and pagination.
    Supports LangChain message format serialization.

    Fields:
        - tool_calls: Structured tool call data (LangChain parsed format) for AI messages
        - additional_kwargs: Provider-specific extras (raw formats, usage stats, etc.)
        - session_id: Customized session ID for session tracking
        - agent_id: Current agent executing this message
        - message_metadata: System metadata (NOT sent to LLM): {parent_message_id, parent_agent_id, session_context, internal_flags}
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_messages_thread_created_id", "thread_id", "created_at", "id"),
        Index("idx_chat_messages_thread_summarized", "thread_id", "is_summarized"),
        Index("idx_chat_messages_thread_type_created", "thread_id", "type", "created_at", "id"),
        Index("idx_chat_messages_message_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="Database record ID")
    message_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, comment="LangChain message ID for deduplication"
    )
    thread_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, comment="human, ai, tool, system")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_summarized: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="0",
        index=True,
        comment="Whether this message has been summarized",
    )
    tool_calls: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, comment="Structured tool call data (LangChain parsed format)"
    )
    additional_kwargs: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Provider-specific extras (raw formats, usage stats)"
    )
    session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Customized session ID for session tracking"
    )
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Current agent executing this message")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Message timestamp when created in conversation",
    )
    message_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="System metadata (NOT sent to LLM): {parent_message_id, parent_agent_id, session_context, internal_flags}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    thread: Mapped["ChatThread"] = relationship("ChatThread", back_populates="messages")


class HitlApproval(Base):
    """HITL approval record for tool calls requiring human confirmation."""

    __tablename__ = "hitl_approvals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "proposal_id", name="uq_hitl_proposal"),
        Index("idx_hitl_pending", "tenant_id", "status", "expires_at"),
        Index("idx_hitl_thread", "tenant_id", "thread_id", "created_at"),
        Index("idx_hitl_agent", "tenant_id", "agent_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_id: Mapped[int] = mapped_column(Integer, nullable=False)

    proposal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_args: Mapped[dict] = mapped_column(JSON, nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class SessionSummary(Base):
    """Session-level summary for individual user interactions."""

    __tablename__ = "session_summaries"
    __table_args__ = (
        Index("idx_session_summaries_thread", "thread_id", "created_at"),
        Index("idx_session_summaries_session", "session_id"),
        Index("idx_session_summaries_thread_summarized", "thread_id", "included_in_thread_summary"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True, comment="Unique session ID"
    )
    thread_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Summary content
    user_intent: Mapped[str] = mapped_column(Text, nullable=False, comment="User's intent in this session")
    tools_used: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="List of tools used in this session"
    )
    key_results: Mapped[str] = mapped_column(Text, nullable=False, comment="Key results summary")
    summary_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional detailed summary generated by LLM"
    )

    # Metadata
    message_range: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Message time range: {from_time, to_time, count}"
    )

    # Thread summary tracking
    included_in_thread_summary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="Whether this session has been included in a thread summary",
    )
    thread_summary_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Thread summary version that includes this session"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    thread: Mapped["ChatThread"] = relationship("ChatThread", back_populates="session_summaries")
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")


class ThreadSummary(Base):
    """Thread-level summary covering multiple sessions."""

    __tablename__ = "thread_summaries"
    __table_args__ = (
        Index("idx_thread_summaries_thread_version", "thread_id", "version"),
        Index("idx_thread_summaries_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Summary version, incremented for each new summary"
    )

    # Summary content
    summary_content: Mapped[str] = mapped_column(Text, nullable=False, comment="Thread summary text")

    # Range metadata
    session_range: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Session range: {from_session_id, to_session_id, session_count}",
    )
    message_range: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Message time range: {from_time, to_time, count}"
    )

    # Statistics
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="Number of sessions covered")
    token_count_before: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Total tokens before summarization"
    )
    token_count_after: Mapped[int] = mapped_column(Integer, nullable=False, comment="Token count of the summary itself")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    thread: Mapped["ChatThread"] = relationship("ChatThread", back_populates="thread_summaries")
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")


class DocumentCollection(Base):
    """Document collection — permission container for knowledge base documents."""

    __tablename__ = "document_collections"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_document_collection_tenant_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="document_collections", lazy="noload")
    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="collection",
        lazy="noload",
    )


class Document(Base):
    """Document model."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "collection_id", "file_hash", name="uq_document_tenant_collection_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    collection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_collections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="SHA256 hash for deduplication"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing", server_default="processing")
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Uploader user ID (metadata only, not used for authz)",
    )
    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="documents", lazy="noload")
    collection: Mapped["DocumentCollection"] = relationship(
        "DocumentCollection", back_populates="documents", lazy="noload"
    )
    owner_user: Mapped["User | None"] = relationship("User", back_populates="documents", foreign_keys=[owner_id])


class DocumentSourceProvider(Base):
    """Tenant-level OAuth app config for external document sources."""

    __tablename__ = "document_source_providers"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_document_source_provider_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="google_drive", server_default="google_drive"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class DocumentSourceOAuthState(Base):
    """Short-lived PKCE OAuth state for an in-flight document source connect."""

    __tablename__ = "document_source_oauth_states"
    __table_args__ = (UniqueConstraint("state", name="uq_document_source_oauth_state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_source_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    source_provider: Mapped["DocumentSourceProvider"] = relationship(
        "DocumentSourceProvider",
        lazy="noload",
    )


class DocumentSourceConnection(Base):
    """User OAuth connection to an external document source."""

    __tablename__ = "document_source_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "owner_id", "provider_id", name="uq_document_source_connection_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_source_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    oauth_credentials_enc: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    source_provider: Mapped["DocumentSourceProvider"] = relationship(
        "DocumentSourceProvider",
        lazy="noload",
    )
    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")
    connectors: Mapped[list["DocumentSyncConnector"]] = relationship(
        "DocumentSyncConnector",
        back_populates="source_connection",
        lazy="noload",
    )


class DocumentSyncConnector(Base):
    """Binds an external folder to a document collection for sync."""

    __tablename__ = "document_sync_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "collection_id", name="uq_document_sync_connector_collection"),
        UniqueConstraint(
            "source_connection_id",
            "source_folder_id",
            name="uq_document_sync_connector_folder",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    source_connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_source_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_folder_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_folder_name: Mapped[str] = mapped_column(String(500), nullable=False)
    include_subfolders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    sync_cursor: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    source_connection: Mapped["DocumentSourceConnection"] = relationship(
        "DocumentSourceConnection",
        back_populates="connectors",
        lazy="noload",
    )


class DocumentExternalFile(Base):
    """Maps an external file ID to an internal document for sync tracking."""

    __tablename__ = "document_external_files"
    __table_args__ = (UniqueConstraint("connector_id", "external_file_id", name="uq_document_external_file"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_sync_connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_file_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_name: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class DataSource(Base):
    """Data source model for tenant analytics data and external connections."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, comment="sqlite, postgres, mysql, databricks, etc.")
    managed: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="1",
        comment="Whether this data source is managed by the platform",
    )
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    asset_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Cached count of assets in this data source",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="data_sources", lazy="noload")
    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")
    assets: Mapped[list["AssetMetadata"]] = relationship(
        "AssetMetadata", back_populates="data_source", cascade="all, delete-orphan", lazy="noload"
    )
    live_apps: Mapped[list["LiveApp"]] = relationship("LiveApp", back_populates="data_source", lazy="noload")

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_datasource_tenant_name"),)


class LiveApp(Base):
    """Live app metadata for tenant-scoped runtime apps."""

    __tablename__ = "live_apps"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_live_apps_tenant_name"),
        Index("idx_live_apps_tenant_status", "tenant_id", "status"),
        Index("idx_live_apps_data_source", "data_source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_file: Mapped[str] = mapped_column(
        String(255), nullable=False, default="entry.html", server_default="entry.html"
    )
    app_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    sdk_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0", server_default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="live_apps", lazy="noload")
    owner_user: Mapped["User | None"] = relationship(
        "User", back_populates="created_live_apps", foreign_keys=[owner_id]
    )
    data_source: Mapped["DataSource | None"] = relationship("DataSource", back_populates="live_apps", lazy="noload")


class LLMProvider(Base):
    """Tenant-configured LLM provider credentials."""

    __tablename__ = "llm_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "display_name", name="uq_llm_providers_tenant_display_name"),
        Index("idx_llm_providers_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preset_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="openai-compatible", server_default="openai-compatible")
    api_base: Mapped[str] = mapped_column(String(1024), nullable=False)
    embedding_api_base: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="llm_providers", lazy="noload")
    model_profiles: Mapped[list["LLMModelProfile"]] = relationship(
        "LLMModelProfile", back_populates="provider", cascade="all, delete-orphan", lazy="noload"
    )


class LLMModelProfile(Base):
    """Tenant-configured model profile (LLM or embedding)."""

    __tablename__ = "llm_model_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_llm_model_profiles_tenant_name"),
        Index("idx_llm_model_profiles_tenant_category", "tenant_id", "category"),
        Index("idx_llm_model_profiles_provider", "provider_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("llm_providers.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    catalog_model_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="preset", server_default="preset")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="llm_model_profiles", lazy="noload")
    provider: Mapped["LLMProvider"] = relationship("LLMProvider", back_populates="model_profiles", lazy="noload")


class ApiConnector(Base):
    """API connector configuration for tenant-scoped external APIs."""

    __tablename__ = "api_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_api_connectors_tenant_name"),
        Index("idx_api_connectors_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False, default="none", server_default="none")
    auth_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    rate_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    schema_source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    schema_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    schema_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_connectors", lazy="noload")
    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")
    operations: Mapped[list["ApiOperationIndex"]] = relationship(
        "ApiOperationIndex", back_populates="connector", cascade="all, delete-orphan", lazy="noload"
    )


class ApiOperationIndex(Base):
    """Current queryable operation index for API connectors."""

    __tablename__ = "api_operation_index"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_id", "operation_uid", name="uq_api_operation_tenant_connector_uid"),
        UniqueConstraint(
            "tenant_id",
            "connector_id",
            "source",
            "upstream_key",
            name="uq_api_operation_tenant_connector_source_upstream",
        ),
        Index("idx_api_operation_tenant_connector", "tenant_id", "connector_id"),
        Index("idx_api_operation_tenant_status", "tenant_id", "status"),
        Index("idx_api_operation_tenant_method", "tenant_id", "method"),
        Index("idx_api_operation_tenant_connector_source", "tenant_id", "connector_id", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_connectors.id", ondelete="CASCADE"), nullable=False
    )
    operation_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path_template: Mapped[str] = mapped_column(String(1024), nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    request_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    auth_requirement: Mapped[str] = mapped_column(String(20), nullable=False, default="none", server_default="none")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default="medium")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="imported", server_default="imported")
    upstream_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    connector: Mapped["ApiConnector"] = relationship("ApiConnector", back_populates="operations", lazy="noload")


class AssetMetadata(Base):
    """Asset metadata model for tables, views, and other queryable data assets."""

    __tablename__ = "asset_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="table",
        server_default="table",
        comment="table, view, materialized_view, api_endpoint",
    )
    columns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_info: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_metadata_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful metadata sync from source database",
    )
    last_metadata_sync_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last metadata sync error message",
    )

    # Relationships
    data_source: Mapped["DataSource"] = relationship(
        "DataSource",
        back_populates="assets",
        lazy="noload",  # Prevent lazy loading in async context
    )
    owner_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[owner_id],
        lazy="noload",
    )

    __table_args__ = (UniqueConstraint("data_source_id", "asset_name", name="uq_asset_datasource_name"),)


class TempTableMetadata(Base):
    """Temporary table metadata for tracking and cleanup.

    Temporary tables are created in tenant's Analytics DB for:
    - Cross-datasource join results
    - Materialized views for large query results
    - Intermediate analysis results

    Naming convention: _temp_{thread_id}_{table_name}_{timestamp}
    """

    __tablename__ = "temp_table_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    thread_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Thread ID (format: {tenant_id}_{user_id}_{agent_id})",
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        comment="Always points to tenant's Analytics DB",
    )
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    meta_info: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Additional metadata: source info, query, columns, etc.",
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Expiration time for automatic cleanup",
    )

    __table_args__ = (
        Index("idx_temp_table_tenant_thread", "tenant_id", "thread_id"),
        Index("idx_temp_table_expires", "expires_at"),
        UniqueConstraint("data_source_id", "table_name", name="uq_temp_table_ds_name"),
    )


class AgentMetricsEventDBModel(Base):
    """Agent metrics event storage (SQLite/Postgres compatible).

    Stores raw metrics events for agent execution tracking, auditing, and billing.
    Designed to work with both SQLite (development) and PostgreSQL (production).
    """

    __tablename__ = "agent_metrics_events"

    # Primary Key (use Integer for SQLite compatibility with autoincrement)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)

    # Event metadata
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Core identifiers (indexed for efficient queries)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Complete context as JSON (SQLite uses TEXT, Postgres uses JSONB)
    context: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Extra context for optional large-capacity data (tool input/output previews, etc.)
    # Stored separately for selective querying to improve performance
    extra_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Metrics: Token Usage (flat for aggregation)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Metrics: Performance
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)

    # Metrics: Data Sizes (Tool)
    input_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error Information
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_events_session_id", "session_id"),
        Index("idx_events_thread_id", "thread_id"),
        Index("idx_events_tenant_time", "tenant_id", "timestamp"),
        Index("idx_events_user_time", "user_id", "timestamp"),
        Index("idx_events_agent_time", "agent_id", "timestamp"),
    )


class TaskRun(Base):
    """Universal task execution history for all background tasks.

    Unified run record for both system (hardcoded) and user-defined scheduled tasks.

    Design:
    - scheduled_task_id links to the ScheduledTask when driven by the scheduler
    - tenant_id/orchestration_run_id enable cross-source observability
    - task_type is the canonical execution/origin label
    - attempt tracks retry count (1-based)
    - Tenant info also kept in input_params for audit/replay convenience
    """

    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="vector_sync, asset_sync, agent_run, etc."
    )
    task_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="Human-readable task name")
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="pending, running, success, failed")
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, comment="manual, scheduled")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Task execution result: return value from task function",
    )
    input_params: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Task input parameters for audit/replay",
    )
    # Unified observability fields
    scheduled_task_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scheduled_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ScheduledTask that triggered this run (null for standalone system tasks)",
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Tenant scope for this run",
    )
    orchestration_run_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Cross-service correlation ID for full-chain tracing",
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Retry attempt number (1-based)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_task_runs_type_started", "task_type", "started_at"),
        Index("idx_task_runs_status", "status"),
        Index("idx_task_runs_scheduled_task", "scheduled_task_id"),
        Index("idx_task_runs_orchestration_run", "orchestration_run_id"),
        Index("idx_task_runs_tenant_started", "tenant_id", "started_at"),
    )


class ScheduledTask(Base):
    """Unified scheduled task definition for system, agent, liveapp, and skill tasks."""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("idx_scheduled_tasks_status_next_run", "status", "next_run_at"),
        Index("idx_scheduled_tasks_status_lease_expires", "status", "lease_expires_at"),
        Index("idx_scheduled_tasks_tenant_user", "tenant_id", "user_id"),
        Index("idx_scheduled_tasks_tenant_owner", "tenant_id", "owner_id"),
        Index("idx_scheduled_tasks_type", "task_type"),
        Index("idx_scheduled_tasks_tenant_stable_key", "tenant_id", "stable_key"),
        UniqueConstraint("tenant_id", "stable_key", name="uq_scheduled_tasks_tenant_stable_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Unified owner field for ACL/ABAC",
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="agent_run, skill_call, liveapp_job, system",
    )
    task_config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Type-specific payload",
    )
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="once, cron")
    schedule_spec: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Schedule definition payload",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending, running, completed, failed, paused, cancelled",
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_instance_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Scheduler instance that currently owns the execution lease",
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last heartbeat time from the owner scheduler instance",
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Execution lease expiration time for distributed scheduler ownership",
    )
    fencing_token: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Monotonic token incremented on each claim/reclaim to fence stale writers",
    )
    notification_channels: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Per-task notification channel overrides",
    )
    # Unified framework fields
    stable_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Stable idempotent key for system task upsert; unique per tenant when set",
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="internal",
        server_default="internal",
        comment="Execution mode: internal (in-process handler) or sandbox (Docker)",
    )
    handler_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Execution entry: 'module:fn' for internal; 'skill:{id}' or 'liveapp:{id}' for sandbox",
    )
    input_params: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Dynamic per-execution input parameters (distinct from static task_config)",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")


class Notification(Base):
    """Notification inbox for in-app delivery."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user_created", "tenant_id", "user_id", "created_at"),
        Index("idx_notifications_user_read", "tenant_id", "user_id", "is_read"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotificationChannelConfig(Base):
    """Tenant-level notification channel configuration."""

    __tablename__ = "notification_channel_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_type", name="uq_notification_channel_tenant_type"),
        Index("idx_notification_channel_tenant_enabled", "tenant_id", "is_enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="email, slack, wecom, dingding")
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class UserNotificationPreference(Base):
    """Per-user notification channel preferences."""

    __tablename__ = "user_notification_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "event_type", name="uq_user_notification_pref"),
        Index("idx_user_notification_pref_user", "tenant_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, comment="scheduled_task_completed or *")
    channels: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
        comment="Allowed delivery channels",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Dashboard(Base):
    """Dashboard model for BI dashboard configurations."""

    __tablename__ = "dashboards"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_dashboard_tenant_name"),
        Index("idx_dashboards_tenant", "tenant_id"),
        Index("idx_dashboards_owner", "tenant_id", "owner_id"),
        Index("idx_dashboards_owner_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Unified owner field for ACL/ABAC",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="dashboards", lazy="noload")


class Artifact(Base):
    """Artifact registry table.

    Records artifacts (Dashboard, Chart, Report, etc.) created by users.
    Thread linkage is optional so artifacts can outlive thread lifecycle and
    also support future manually-created artifacts.

    Design:
        - thread_id: Optional reference to source thread (no foreign key cascade)
        - resource_id: Plain integer (NO CASCADE - preserve artifact when thread deleted)
        - Artifacts belong to users (via owner_id), not threads
        - Deleting thread does not delete artifacts
    """

    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "artifact_type", "resource_id", name="uq_artifact_resource"),
        Index("idx_artifacts_type", "artifact_type"),
        Index("idx_artifacts_resource", "artifact_type", "resource_id"),
        Index("idx_artifacts_tenant_owner_type", "tenant_id", "owner_id", "artifact_type"),
        Index("idx_artifacts_created", text("created_at DESC")),
        Index("idx_artifacts_user_gallery", "tenant_id", "owner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant owning this artifact",
    )
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        comment="Unified owner field for ACL/ABAC",
    )
    source_thread_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original thread where artifact was generated (optional)",
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    links: Mapped[list["ArtifactLink"]] = relationship(
        "ArtifactLink",
        back_populates="artifact",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")


class ArtifactLink(Base):
    """Optional link between an artifact and a chat thread."""

    __tablename__ = "artifact_links"
    __table_args__ = (
        UniqueConstraint("artifact_id", "thread_id", name="uq_artifact_link"),
        Index("idx_artifact_links_thread", "thread_id"),
        Index("idx_artifact_links_artifact", "artifact_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    artifact: Mapped["Artifact"] = relationship("Artifact", back_populates="links", lazy="noload")
    thread: Mapped["ChatThread"] = relationship("ChatThread", back_populates="artifact_links", lazy="noload")


class Report(Base):
    """Persisted report content generated by agents or users.

    Reports are first-class resources and are intentionally decoupled from
    thread lifecycle so they remain available even after a thread is deleted.
    """

    __tablename__ = "reports"
    __table_args__ = (
        Index("idx_reports_tenant_created", "tenant_id", "created_at"),
        Index("idx_reports_tenant_owner_created", "tenant_id", "owner_id", "created_at"),
        Index("idx_reports_user_owner", "tenant_id", "owner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="Unified owner field for ACL/ABAC",
    )
    source_thread_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original thread ID where the report was generated (no FK by design)",
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="markdown", server_default="markdown")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    report_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    owner_user: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id], lazy="noload")


class AclPrincipal(Base):
    """Principal registry for unified ACL (user/role)."""

    __tablename__ = "acl_principals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "principal_type", "principal_id", name="uq_acl_principal"),
        Index("idx_acl_principals_tenant_type_id", "tenant_id", "principal_type", "principal_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="user or role")
    principal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ResourceAcl(Base):
    """Resource ownership and ACL metadata entry."""

    __tablename__ = "resource_acl"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_resource_acl_resource"),
        Index("idx_resource_acl_owner", "tenant_id", "owner_id"),
        Index("idx_resource_acl_resource", "tenant_id", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    inherit_from_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    inherit_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AclGrant(Base):
    """Explicit resource grants for principals."""

    __tablename__ = "acl_grants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id",
            "principal_type",
            "principal_id",
            "permission",
            name="uq_acl_grant",
        ),
        Index("idx_acl_grants_resource", "tenant_id", "resource_type", "resource_id"),
        Index("idx_acl_grants_principal", "tenant_id", "principal_type", "principal_id", "permission"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    principal_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="user or role")
    principal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False, comment="read, write, manage")
    effect: Mapped[str] = mapped_column(String(10), nullable=False, default="allow", server_default="allow")
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class TagKey(Base):
    """Tag key model."""

    __tablename__ = "tag_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tag_keys_tenant_name"),
        Index("idx_tag_keys_tenant", "tenant_id"),
        Index("idx_tag_keys_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TagValue(Base):
    """Tag value model."""

    __tablename__ = "tag_values"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key_id", "value", name="uq_tag_values_tenant_key_value"),
        Index("idx_tag_values_tenant", "tenant_id"),
        Index("idx_tag_values_key", "tenant_id", "key_id"),
        Index("idx_tag_values_rank", "tenant_id", "key_id", "rank"),
        Index("idx_tag_values_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    key_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tag_keys.id", ondelete="CASCADE"), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TagBinding(Base):
    """Tag binding model."""

    __tablename__ = "tag_bindings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id",
            "tag_value_id",
            name="uq_tag_bindings_tenant_resource_tag_value",
        ),
        Index("idx_tag_bindings_resource", "tenant_id", "resource_type", "resource_id"),
        Index("idx_tag_bindings_tag_value", "tenant_id", "tag_value_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tag_value_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tag_values.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ResourceTagConfig(Base):
    """Resource tag whitelist config."""

    __tablename__ = "resource_tag_configs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "resource_type",
            "tag_key_id",
            name="uq_resource_tag_configs_tenant_resource_key",
        ),
        Index("idx_resource_tag_configs_resource", "tenant_id", "resource_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tag_key_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tag_keys.id", ondelete="CASCADE"), nullable=False)
    value_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AbacPolicy(Base):
    """ABAC policy model."""

    __tablename__ = "abac_policies"
    __table_args__ = (
        Index("idx_abac_policies_tenant", "tenant_id"),
        Index("idx_abac_policies_resource_type", "tenant_id", "resource_type", "status"),
        Index("idx_abac_policies_resource_action", "tenant_id", "resource_type", "action", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="read", server_default="read")
    expression: Mapped[str] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ResourceIndex(Base):
    """Unified resource index for FTS and Vector search synchronization.

    Tracks the indexing status of all searchable resources (documents, assets,
    API connectors) and coordinates synchronization between business data
    and the vector database.

    Design principles:
    - Logical reference via (tenant_id, resource_type, resource_id) - no FK constraints
    - Vector status fields prefixed with 'vector_' for clear separation
    - FTS content stored separately for potential future migration to Elasticsearch
    - indexed_content_hash tracks what was actually synced to VectorDB
    """

    __tablename__ = "resource_index"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_resource_index_tenant_type_id"),
        Index("idx_resource_index_tenant_vector_status", "tenant_id", "vector_status"),
        Index("idx_resource_index_tenant_content_updated", "tenant_id", "content_updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="document, asset, api_connector")
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="Logical reference to resource ID")

    # Denormalized owner/parent info for ABAC/ACL filtering (single-table authorization)
    owner_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="Resource owner user_id for ABAC/ACL filtering"
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Parent resource id (collection_id for documents, data_source_id for assets, connector_id for api_operations)",
    )

    # Source parser that generated raw_content (e.g., "default", "docling", "mineru")
    source_parser: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="default",
        server_default="default",
        comment="Parser used to generate raw_content: default, docling, mineru, etc.",
    )

    # Raw structured content from parser (source of truth)
    raw_content: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Structured content from parser: {text, meta} or custom schema"
    )
    # Tokenized content for FTS (jieba output)
    tokenized_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Jieba-tokenized content for FTS"
    )
    # Note: fts_content_tsvector is a PostgreSQL GENERATED column.
    # It is NOT mapped here because SQLAlchemy's Computed column breaks SQLite tests.
    # Use literal_column("fts_content_tsvector") in repository FTS queries instead.
    vector_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending/indexing/indexed/failed/stale/permanent_failed",
    )
    vector_content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Hash of content that was successfully indexed to VectorDB"
    )
    vector_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last successful vector sync timestamp"
    )
    vector_sync_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last failed vector sync timestamp"
    )
    vector_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Last vector sync error message")
    vector_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="Number of sync retry attempts"
    )
    vector_next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Next allowed retry time (exponential backoff)"
    )

    parse_job_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="External parse job id (e.g. MinerU task_id)"
    )
    parsed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last successful document parse timestamp"
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Last document parse error message")
    parse_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last document parse failure timestamp"
    )
    parse_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="Document parse retry attempts"
    )

    # Common metadata fields
    content_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Content last updated timestamp"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AgentIngressEndpoint(Base):
    """Agent-scoped channel ingress endpoint (Slack bot, WeCom app, etc.)."""

    __tablename__ = "agent_ingress_endpoints"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "platform", name="uq_agent_ingress_endpoint"),
        UniqueConstraint("endpoint_key", name="uq_agent_ingress_endpoint_key"),
        Index("idx_agent_ingress_endpoints_tenant_platform", "tenant_id", "platform", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, server_default="slack")
    endpoint_key: Mapped[str] = mapped_column(String(64), nullable=False)
    external_scope_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    identity_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("identity_sources.id", ondelete="RESTRICT"), nullable=True
    )
    platform_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    credentials_encrypted: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="noload")


class IngressThreadLink(Base):
    """Maps an external channel conversation to a LingQing chat thread."""

    __tablename__ = "ingress_thread_links"
    __table_args__ = (
        UniqueConstraint(
            "endpoint_id",
            "external_channel_id",
            "external_thread_key",
            name="uq_ingress_thread_link",
        ),
        Index("idx_ingress_thread_links_tenant", "tenant_id"),
        Index("idx_ingress_thread_links_thread", "chat_thread_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    endpoint_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_ingress_endpoints.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    external_channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    external_thread_key: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    chat_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )


class SlackProcessedEvent(Base):
    """Idempotency store for Slack Events API callbacks."""

    __tablename__ = "slack_processed_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_slack_processed_event"),
        Index("idx_slack_processed_events_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="Slack event id")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
