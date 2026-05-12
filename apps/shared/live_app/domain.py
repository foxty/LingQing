"""Domain models for live app features."""

from dataclasses import dataclass, field
from enum import StrEnum


class LiveAppAuditEventType(StrEnum):
    """Typed event names for live app audit events."""

    FILE_WRITE = "live_app.file.write"
    DATA_QUERY = "live_app.data.query"
    DATA_MUTATE = "live_app.data.mutate"
    DATA_IMPORT = "live_app.data.import"
    MIGRATION_APPLY = "live_app.migration.apply"
    MIGRATION_ROLLBACK = "live_app.migration.rollback"
    MIGRATION_CREATE = "live_app.migration.create"
    MIGRATION_REMOVE = "live_app.migration.remove"
    COMMIT = "live_app.commit"
    ENVIRONMENT_PROMOTE = "live_app.environment.promote"


@dataclass(frozen=True, slots=True)
class LiveAppMigration:
    """Represents one app migration file pair."""

    name: str
    path: str
    checksum: str
    up_sql: str
    down_path: str | None = None
    down_sql: str | None = None

    @property
    def has_down(self) -> bool:
        return self.down_path is not None


@dataclass(frozen=True, slots=True)
class LiveAppDeploymentState:
    """Current deployed commit pointers across environments."""

    dev: str | None = None
    test: str | None = None
    prod: str | None = None

    @classmethod
    def from_mapping(cls, data: dict | None) -> "LiveAppDeploymentState":
        raw = data or {}
        if not isinstance(raw, dict):
            raw = {}
        return cls(
            dev=raw.get("dev"),
            test=raw.get("test"),
            prod=raw.get("prod"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "dev": self.dev,
            "test": self.test,
            "prod": self.prod,
        }

    def with_environment(self, *, environment: str, commit: str) -> "LiveAppDeploymentState":
        updates = self.to_dict()
        updates[environment] = commit
        return LiveAppDeploymentState.from_mapping(updates)


@dataclass(frozen=True, slots=True)
class LiveAppConfig:
    """Typed config wrapper for live app metadata."""

    deployed_commits: LiveAppDeploymentState = field(default_factory=LiveAppDeploymentState)

    @classmethod
    def from_mapping(cls, data: dict | None) -> "LiveAppConfig":
        raw = data or {}
        if not isinstance(raw, dict):
            raw = {}
        return cls(
            deployed_commits=LiveAppDeploymentState.from_mapping(raw.get("deployed_commits")),
        )

    def to_dict(self) -> dict:
        return {
            "deployed_commits": self.deployed_commits.to_dict(),
        }

    def with_deployed_commit(self, *, environment: str, commit: str) -> "LiveAppConfig":
        return LiveAppConfig(deployed_commits=self.deployed_commits.with_environment(environment=environment, commit=commit))


@dataclass(frozen=True, slots=True)
class LiveAppRecord:
    """Typed app metadata payload for list/get/create APIs."""

    app_id: int
    name: str
    description: str | None
    entry_file: str
    sdk_version: str
    status: str
    data_source_id: int | None
    owner_name: str | None
    deployment_state: LiveAppDeploymentState
    updated_at: str | None = None

    def to_dict(self) -> dict:
        payload = {
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "entry_file": self.entry_file,
            "sdk_version": self.sdk_version,
            "status": self.status,
            "data_source_id": self.data_source_id,
            "owner_name": self.owner_name,
            "deployment_state": self.deployment_state.to_dict(),
        }
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at
        return payload


@dataclass(frozen=True, slots=True)
class LiveAppPromotionMigrationSummary:
    """Migration summary produced by promotion flow."""

    enabled: bool
    schema: str
    total: int
    mode: str
    status: str
    reason: str
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    already_applied: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict | None) -> "LiveAppPromotionMigrationSummary":
        raw = data or {}
        if not isinstance(raw, dict):
            raw = {}
        return cls(
            enabled=bool(raw.get("enabled", False)),
            schema=str(raw.get("schema", "")),
            total=int(raw.get("total", 0)),
            mode=str(raw.get("mode", "apply")),
            status=str(raw.get("status", "success")),
            reason=str(raw.get("reason", "")),
            applied=list(raw.get("applied", [])),
            skipped=list(raw.get("skipped", [])),
            pending=list(raw.get("pending", [])),
            already_applied=list(raw.get("already_applied", [])),
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "schema": self.schema,
            "total": self.total,
            "mode": self.mode,
            "status": self.status,
            "reason": self.reason,
            "applied": self.applied,
            "skipped": self.skipped,
            "pending": self.pending,
            "already_applied": self.already_applied,
        }


@dataclass(frozen=True, slots=True)
class LiveAppPromotionPayload:
    """Typed payload for one promotion execution."""

    app_id: int
    from_environment: str
    to_environment: str
    promoted_files: int
    removed_files: list[str]
    source_commit: str
    dry_run: bool
    migrations: LiveAppPromotionMigrationSummary
    deployment_state: LiveAppDeploymentState
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "app_id": self.app_id,
            "from_environment": self.from_environment,
            "to_environment": self.to_environment,
            "promoted_files": self.promoted_files,
            "removed_files": self.removed_files,
            "source_commit": self.source_commit,
            "dry_run": self.dry_run,
            "migrations": self.migrations.to_dict(),
            "deployment_state": self.deployment_state.to_dict(),
        }
        if self.warnings:
            result["warnings"] = self.warnings
        return result


@dataclass(frozen=True, slots=True)
class LiveAppPromotionRecord:
    """Typed promotion record projected from audit events."""

    created_at: str | None
    actor_user_id: int | None
    from_environment: str | None
    to_environment: str | None
    source_commit: str | None
    promoted_files: int
    removed_files: list[str]
    migrations: LiveAppPromotionMigrationSummary

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "actor_user_id": self.actor_user_id,
            "from_environment": self.from_environment,
            "to_environment": self.to_environment,
            "source_commit": self.source_commit,
            "promoted_files": self.promoted_files,
            "removed_files": self.removed_files,
            "migrations": self.migrations.to_dict(),
        }
