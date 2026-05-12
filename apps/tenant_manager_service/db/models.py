"""ORM models for tenant manager P0."""

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Tenant manager ORM base."""


class TenantManagerTenant(Base):
    """Tenant master record for control plane."""

    __tablename__ = "tenant_manager_tenants"
    __table_args__ = (Index("idx_tm_tenants_status_updated", "status", "updated_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_uid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    tenant_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="provisioning", server_default="provisioning"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="CURRENT_TIMESTAMP",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default="CURRENT_TIMESTAMP",
    )


class TenantLifecycleEvent(Base):
    """Lifecycle state change history."""

    __tablename__ = "tenant_manager_lifecycle_events"
    __table_args__ = (Index("idx_tm_lifecycle_tenant_created", "tenant_uid", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_uid: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenant_manager_tenants.tenant_uid", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="CURRENT_TIMESTAMP",
    )


class TenantManagerAuditLog(Base):
    """Append-only audit logs for tenant manager actions."""

    __tablename__ = "tenant_manager_audit_logs"
    __table_args__ = (
        Index("idx_tm_audit_tenant_created", "tenant_uid", "created_at"),
        Index("idx_tm_audit_action_created", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_uid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="CURRENT_TIMESTAMP",
    )


class TenantManagerUser(Base):
    """Local control-plane user for tenant manager (native provider)."""

    __tablename__ = "tenant_manager_users"
    __table_args__ = (Index("idx_tm_users_status_updated", "status", "updated_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="platform_ops", server_default="platform_ops")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="CURRENT_TIMESTAMP",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default="CURRENT_TIMESTAMP",
    )
